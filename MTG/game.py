import sys
import os
import traceback
import time
import pdb
import copy

from MTG import player
from MTG import zone
from MTG import cards
from MTG import gamesteps
from MTG import combat
from MTG import triggers
from MTG.exceptions import *
from MTG.utils import path_from_home


class Game(object):
    """A game object. This represents the entire state of an in-progress MTG game.

    """

    # Give each player their deck.
    def __init__(self, decks, test=False):
        self.stack = zone.Stack()
        self.stack.game = self
        self.passed_priority = 0
        self.step = None
        self.pending_turns = []
        self.pending_steps = []
        self.test = test
        self.turn_num = 0
        self.num_players = len(decks)
        self.players_list = [player.Player(decks[i], 'player' + str(i), game=self)
                             for i in range(self.num_players)]
        # self.players = cycle(self.players_list)

        # self.previous_state = GAME_PREVIOUS_STATE
        self.recording_replay = False
        self.replay = None

    def __getstate__(self):

        state = self.__dict__.copy()
        state["recording_replay"] = False
        state["replay"] = None

        return state

    def __setstate__(self, state):

        self.__dict__.update(state)
        self.recording_replay = False
        self.replay = None

    @property
    def timestamp(self):
        return (self.turn_num * 100
                + self.step._value_
                + time.time() % 10**4 / 10**4)  # this is a float less than 1

    @property
    def eot_time(self):
        return self.turn_num * 100 + gamesteps.Step.CLEANUP._value_

    @property
    def APNAP(self):
        i = self.players_list.index(self.current_player)
        return self.players_list[i:] + self.players_list[:i]

    def opponent(self, player):
        """Opponents -- return a single player in 2p game"""
        assert player in self.players_list
        op = [p for p in self.players_list if p != player]
        if isinstance(op, list) and len(op) == 1:
            return op[0]

        return op

    def apply_to_players(self, func):
        return [func(p) for p in self.players_list]

    def add_static_effect(self, name, value, source, toggle_func):
        for p in self.players_list:
            p.add_static_effect(name, value, source, toggle_func)

    def trigger(self, condition, source=None, amount=1):
        for p in self.players_list:
            p.trigger(condition, source, amount)


    def apply_stack_item(self, stack_item):
        """ resolving a spell/effect from stack, removing it from the stack """
        print(stack_item)
        stack_item.apply()
        self.stack.remove(stack_item)


    def apply_to_zone(self, apply_func, _zone, condition=lambda p: True):
        """Apply some function to all cards in a certain zone

        - filter out by a condition function if necessary
        - defaults to all cards

        return True if at least one object satisfied the condition
        """

        if isinstance(_zone, str):
            _zone = zone.str_to_zone_type(_zone)

        did_something = any([plyr.apply_to_zone(apply_func, _zone, condition)
                             for plyr in self.players_list])

        return did_something


    def apply_to_battlefield(self, apply_func, condition=lambda p: True):
        return self.apply_to_zone(apply_func, zone.ZoneType.BATTLEFIELD, condition)


    # TODO
    def apply_state_based_actions(self):
        # iterate through cards that could possibly cause a state-based action
        _any_action = False
        def any_action():
            nonlocal _any_action
            _any_action = True

        self.apply_to_battlefield(
            lambda p: any_action() if p.zone.remove(p) else None,
            lambda p: p.is_token and not p.zone.is_battlefield)

        self.apply_to_battlefield(
            lambda p: any_action() if p.check_effect_expiration() else None)

        self.apply_to_battlefield(
            lambda p: any_action() if p.destroy() else None,
            lambda p: p.is_creature and
                      p.status.damage_taken >= p.toughness)

        self.apply_to_battlefield(
            lambda p: any_action() if p.change_zone(p.owner.graveyard) else None,
            lambda p: p.is_aura and
                      p.enchant_target is None)

        # check for player death
        for _player in self.players_list:
            if _player.life <= 0:
                _player.lose()
            if _player.lost:  # TODO: PROBLEM with multiplayer -- maybe skip over rest of turn / destroy all cards owned by that player?
                any_action()
                self.players_list.remove(_player)
                self.num_players -= 1

        if self.num_players <= 1:
            raise GameOverException

        if _any_action:
            print("Applying state based actions")
            self.apply_state_based_actions()



    def handle_priority(self, step, priority=None):

        # priority tracks the index of the player that currently have priority
        if priority is None:
            priority = self.players_list.index(self.current_player)

        self.passed_priority = 0

        # while not everyone has passed priority
        while self.passed_priority < self.num_players or self.stack:
            # TODO: repeat state-based-actions & checking for triggers
            #       UNTIL none avaliable
            self.apply_state_based_actions()


            for p in self.APNAP:
                if p.pending_triggers:
                    # ask player for order
                    triggers = []
                    if len(p.pending_triggers) > 1 and not p.autoOrderTriggers:
                        ans = p.make_choice("Current triggers: %r\n"
                                            "Would you like to order them, %r?\n"
                                            "Enter a space separated list of indices, "
                                            "starting from the trigger you'd like to put on the"
                                            "bottom of the stack.\n"
                                            % (p.pending_triggers, p))

                        try:
                            ans = ans.split(" ")
                            for ind in ans:
                                ind = int(ind)
                                triggers.append(p.pending_triggers[ind])
                        except (IndexError, ValueError):
                            print("Error reading order. Auto-ordering.")
                            pass

                    for trig in p.pending_triggers:
                        if trig not in triggers:
                            triggers.append(trig)

                    triggers = [t.put_on_stack() for t in triggers]
                    self.stack.elements.extend([t for t in triggers if t is not None])
                    p.pending_triggers = []
                    self.passed_priority = 0

            if self.stack:
                print("\nstack: ", self.stack[::-1])

            # check if player auto pass priority
            if self.players_list[priority].passPriorityUntil not in [None, step]:
                _play = None
            else:
                self.players_list[priority].passPriorityUntil = None
                # ask current player for an action
                # get_action() will return '__continue' if we're debugging and executing code directly
                # this allows us to manipulate game state without anyone receiving priority
                _play = self.players_list[priority].get_action()


            if _play is None:  # a player passes priority
                self.passed_priority += 1
                priority = (priority + 1) % self.num_players
                if self.passed_priority == self.num_players and self.stack:
                    # resolve top stack item; active player gets priority
                    self.apply_stack_item(self.stack[-1])
                    self.passed_priority = 0
                    priority = self.players_list.index(self.current_player)

            elif _play == '__continue':
                pass  # debug
            else:
                # new thing on top of stack; must have everyone re-pass priority
                self.passed_priority = 0

                if _play.is_mana_ability or _play.is_special_action:
                    # applies instantly
                    _play.apply()
                else:
                    self.stack.add(_play)  # add to stack

            if self.recording_replay:
                previous_gamestate = copy.deepcopy(self)
                previous_gamestate.current_step = step
                self.replay.append(previous_gamestate)

    def handle_beginning_phase(self, step):
        if step is gamesteps.Step.UNTAP:
            self.apply_to_battlefield(lambda p: p.untap(),
                                      lambda p: p.controller is self.current_player)
            for _player in self.players_list:
                _player.landPlayed = 0

        elif step is gamesteps.Step.UPKEEP:
            self.trigger(triggers.triggerConditions.onUpkeep)
            self.handle_priority(step)

        elif step is gamesteps.Step.DRAW:
            if self.first_player_does_not_draw:
                self.first_player_does_not_draw = False
            else:
                self.current_player.draw()
            self.handle_priority(step)

    # TODO
    def handle_main_phase(self, step):
        self.handle_priority(step)


    # TODO
    def handle_combat_phase(self, step):
        if step is gamesteps.Step.BEGINNING_OF_COMBAT:
            self.trigger(triggers.triggerConditions.onEnterCombat)

        elif step is gamesteps.Step.DECLARE_ATTACKERS:
            self.trigger(triggers.triggerConditions.onDeclareAttackers)

        elif step is gamesteps.Step.DECLARE_BLOCKERS:
            self.trigger(triggers.triggerConditions.onDeclareBlockers)

        elif step is gamesteps.Step.END_OF_COMBAT:
            self.trigger(triggers.triggerConditions.onEndofCombat)

        if step is gamesteps.Step.DECLARE_ATTACKERS:

            # GAME_PREVIOUS_STATE = deepcopy(self)
            ok = False
            while not ok:
                pending_attackers = {p: [] for p in self.players_list}

                avaliable_attackers = []
                self.apply_to_battlefield(
                    lambda p: avaliable_attackers.append(p),
                    lambda p: p.controller == self.current_player and p.can_attack())

                if not avaliable_attackers:  # no attacks; skip rest of combat
                    for p in self.players_list:
                        if p.passPriorityUntil is None:
                            p.passPriorityUntil = gamesteps.Step.POSTCOMBAT_MAIN
                    break

                print("Creatures that can attack:", avaliable_attackers)

                for defender in self.players_list:
                    if defender == self.current_player:
                        continue

                    # declare attackers
                    # space-separated list of indices of creatures in avaliable_attackers, starting at 0
                    answer = self.current_player.make_choice(
                        "\n{}, Choose all creatures you'd like to attack {} with\n"
                        .format(self.current_player, defender.name))
                    if self.test:
                        print(answer)

                    if answer:
                        # TODO: planeswalkers
                        try:
                            answer = answer.split(" ")
                            for ind in answer:
                                ind = int(ind)
                                if ind < len(avaliable_attackers):
                                    pending_attackers[defender].append(avaliable_attackers[ind])
                                    # avaliable_attackers[ind].attacks(
                                        # defender)

                                else:
                                    print("creature #{} is out of bounds\n"
                                          .format(str(ind)))
                                    continue

                        except:
                            traceback.print_exc()
                            print("wrong format: {}\n".format(ind))
                            continue

                # simulate attacking
                for defender, atkrs in pending_attackers.items():
                    for atkr in atkrs:
                        atkr.status.is_attacking = defender

                ok = combat.check_valid_attack(self.current_player)

                # reset simulation
                for defender, atkrs in pending_attackers.items():
                    for atkr in atkrs:
                        atkr.status.is_attacking = []

                if not ok:
                    print("Illegal attack; rewind\n\n")
                    # self = deepcopy(GAME_PREVIOUS_STATE)
                    continue
                else:
                    for defender, atkrs in pending_attackers.items():
                        for atkr in atkrs:
                            atkr.attacks(defender)

            for creature in avaliable_attackers:
                print("{} is attacking {}\n".format(
                    creature.name, creature.status.is_attacking))

            # check remove-from-combat abilities/events

        if step is gamesteps.Step.DECLARE_BLOCKERS:
            # TODO: need to figure out which player's turn / priority

            # MULTIPLAYER: refactor code / when-to-rewind

            # GAME_PREVIOUS_STATE = deepcopy(self)
            ok = False
            while not ok:
                pending_blocks = []

                for defender in self.players_list:
                    if defender == self.current_player:  # only current player's opponents need to block
                        continue

                    currently_attacking = []  # get all attacking creatures
                    self.apply_to_battlefield(
                        lambda p: currently_attacking.append(p),
                        lambda p: p.status.is_attacking == defender)

                    if currently_attacking:
                        print("Creatures attacking {}: {}\n\n".format(
                            defender, currently_attacking))

                        can_block = []
                        self.apply_to_battlefield(
                            lambda p: can_block.append(p),
                            lambda p: p.controller == defender and p.can_block())

                        if can_block:
                            print("Potential blockers: {}\n".format(can_block))

                            # declare blockers


                            for attacking_creature in currently_attacking:
                                _ok = False
                                while not _ok:
                                    answer = defender.make_choice("\n{}, Choose all creatures you'd like to block {} with\n"
                                                                  .format(defender, attacking_creature))

                                    if self.test:
                                        print(answer)
                                    if not answer:
                                        break

                                    try:
                                        # TODO: menace / multiple-blocking
                                        answer = answer.split(" ")
                                        for ind in answer:
                                            ind = int(ind)
                                            if ind < len(can_block):
                                                pending_blocks.append((can_block[ind], attacking_creature))
                                            else:
                                                print(
                                                    "creature #{} is out of bounds\n".format(ind))
                                                continue

                                        _ok = True

                                    except:
                                        traceback.print_exc()
                                        print(
                                            "wrong format: {}\n".format(answer))

                    # TODO: attacker declare multi-block dmg order
                    # TODO: check for menace

                    # simulate blocker.blocks(attacker) without causing any triggers
                    for blocker, attacker in pending_blocks:
                        blocker.status.is_blocking.append(attacker)
                    ok = combat.check_valid_block(
                        self.current_player, defender)

                    # clear simulation
                    for blocker, attacker in pending_blocks:
                        blocker.status.is_blocking.remove(attacker)


                    if not ok:
                        print("Illegal block; rewind\n\n")
                        
                        # self = GAME_PREVIOUS_STATE
                        break
                    else:
                        # legal block; actually execute blocking action
                        for blocker, attacker in pending_blocks:
                            blocker.blocks(attacker)

            for creature in currently_attacking:
                print("{} is attacking {}\n".format(
                    creature.name, creature.status.is_attacking))

        if step is gamesteps.Step.FIRST_STRIKE_COMBAT_DAMAGE:
            # if no first strikes avaliable, skip to combat damage
            if not self.apply_to_battlefield(
                    lambda p: p.deals_damage(
                        p.status.is_attacking, p.power, is_combat=True),
                    lambda p: p.status.is_attacking and (p.has_ability("First Strike")
                                                         or p.has_ability("Double Strike"))):

                for p in self.players_list:
                    if p.passPriorityUntil is None:
                        p.passPriorityUntil = gamesteps.Step.COMBAT_DAMAGE


        if step is gamesteps.Step.COMBAT_DAMAGE:
            # attackers do damage
            self.apply_to_battlefield(
                lambda p: p.deals_damage(p.status.is_attacking,
                                         p.power, is_combat=True),
                lambda p: p.status.is_attacking and (not p.has_ability("First Strike")
                                                     or p.has_ability("Double Strike")))

            # blockers do damage
            self.apply_to_battlefield(
                lambda p: p.deals_damage(p.status.is_blocking,
                                         p.power, is_combat=True),
                lambda p: p.status.is_blocking and (not p.has_ability("First Strike")
                                                    or p.has_ability("Double Strike")))

            # damage resolve / triggers

        if step is gamesteps.Step.END_OF_COMBAT:
            self.apply_to_battlefield(
                lambda p: p.exits_combat())
            pass

        self.handle_priority(step)

    def handle_end_phase(self, step):
        if step is gamesteps.Step.END:
            self.apply_to_battlefield(
                lambda p: p.trigger(triggers.triggerConditions.onEndstep))
            self.handle_priority(step)

        elif step is gamesteps.Step.CLEANUP:
            self.current_player.discard(
                down_to=self.current_player.maxHandSize)
            self.apply_to_battlefield(
                lambda p: p.trigger(triggers.triggerConditions.onCleanup))
            self.apply_state_based_actions()
            


    def handle_turn(self):
        self.pending_steps = []
        for phase in gamesteps.Phase:
            self.pending_steps.extend(phase.steps)

        while self.pending_steps:
            self.step = self.pending_steps.pop(0)
            print(self.step)
            {
                gamesteps.Step.UNTAP: self.handle_beginning_phase,
                gamesteps.Step.UPKEEP: self.handle_beginning_phase,
                gamesteps.Step.DRAW: self.handle_beginning_phase,
                gamesteps.Step.PRECOMBAT_MAIN: self.handle_main_phase,
                gamesteps.Step.BEGINNING_OF_COMBAT: self.handle_combat_phase,
                gamesteps.Step.DECLARE_ATTACKERS: self.handle_combat_phase,
                gamesteps.Step.DECLARE_BLOCKERS: self.handle_combat_phase,
                gamesteps.Step.FIRST_STRIKE_COMBAT_DAMAGE: self.handle_combat_phase,
                gamesteps.Step.COMBAT_DAMAGE: self.handle_combat_phase,
                gamesteps.Step.END_OF_COMBAT: self.handle_combat_phase,
                gamesteps.Step.POSTCOMBAT_MAIN: self.handle_main_phase,
                gamesteps.Step.END: self.handle_end_phase,
                gamesteps.Step.CLEANUP: self.handle_end_phase
            }[self.step](self.step)
            for _player in self.players_list:
                _player.mana.clear()

        for _player in self.players_list:
            _player.end_turn()
        self.pending_turns.append(self.current_player)
        self.current_player = self.pending_turns.pop(
            0)  # cycles to next player's turn
        self.turn_num += 1
        return True



    # debug

    # TODO
    # print each player's states
    # print debug variables
    def print_game_state(self):
        print("[Current Game State]\n")

        print("~~~ Stack:\n")
        print(self.stack)
        print('\n')

        for _player in self.players_list:
            _player.print_player_state()

    # def __repr__(self):
    #     return self.print_game_state()

    # TODO
    def setup_game(self):
        print("setting up game...")
        for _player in self.players_list:
            _player.draw(7)
        # everyone gets a turn queued up, in order
        self.pending_turns.extend(self.players_list)
        self.first_player_does_not_draw = True
        self.current_player = self.pending_turns.pop(0)

    def run_game(self):
        self.setup_game()

        while self.num_players > 1:
            try:
                self.handle_turn()
            except GameOverException:
                break
            except GamescriptEnded:
                break


def start_game():
    cards.setup_cards()
    decks = [
        cards.read_deck(path_from_home('card_db/decks/mono_red.txt')),
        cards.read_deck(path_from_home('card_db/decks/mono_green.txt'))
    ]
    game = Game(decks)
    game.run_game()


if __name__ == '__main__':
    start_game()
