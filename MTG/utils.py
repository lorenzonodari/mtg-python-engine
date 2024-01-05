import traceback
import re
import os
import os.path

# any length > 0 of the following: { X, numbers, hybrid e.g. (U/R), WUBRGC }
mana_pattern = re.compile(
    '(X|' '\d|' '(\([WUBRGC2]/[WUBRGC]\))|' '[WUBRGC])+')


def get_card_from_user_input(player, string):
    """Convert a user input (naming a card in a zone) to an actual game object

    b 2 --> 2nd(3rd) card on battlefield
    b Grizzly Bear --> Grizzly Bear on battlefield

    s 0 --> 1st card on stack (from top)

    h -1 --> last card in hand

    og 3 --> 3rd(4th) card on opponent's graveyard
    """
    if not string:
        return None

    if string[0] == 'o':  # opponent; continue parsing rest of string
        string = string[1:]
        player = player.game.opponent(player)

    if string[0] == 'p':
        return player

    if string[0] == 'b':
        zone = player.battlefield
    elif string[0] == 's':
        zone = player.game.stack
    elif string[0] == 'h':
        zone = player.hand
    elif string[0] == 'g':
        zone = player.graveyard
    else:
        return None

    try:
        i = int(string[2:])
        if i < len(zone):
            return zone[i]
        else:
            return None
    except ValueError:
        return zone.get_card_by_name(string[2:])


def choose_targets(source):
    # TODO: ensure boolean/card return values of this func
    # is being parsed correctly.
    if source.target_criterias is None:
        return True

    # No valid targets
    if not source.has_valid_target():
        return False

    targets_chosen = []
    for criteria, prompt in zip(source.target_criterias, source.target_prompts):
        
        # keep choosing until we get a valid target
        # TODO: allow optional targeting;
        # TODO: if no valid target available, fizzles
        card = None
        try:
            while not card:
                answer = source.controller.make_choice(prompt)
                card = get_card_from_user_input(source.controller, answer)
                if card is None: continue
                if not criteria(source, card):
                    card = None
        except:
            traceback.print_exc()
            return False

        targets_chosen.append(card)
    return targets_chosen


def parse_targets(criterias):
    for i, v in enumerate(criterias):
        if v == 'creature':
            criterias[i] = lambda self, p: p.is_permanent and p.is_creature

        if v == 'your creature':
            criterias[i] = lambda self, p: p.is_permanent and p.is_creature and p.controller == self.controller

        if v == 'other creature':
            criterias[i] = lambda self, p: p.is_permanent and p.is_creature and p != self

        if v == 'your other creature':
            criterias[i] = lambda self, p: (p.is_permanent and p.is_creature
                                            and p.controller == self.controller and p != self)

        if v == 'opponent creature':
            criterias[i] = lambda self, p: p.is_creature and p.controller != self.controller

        if v == 'opponent':
            criterias[i] = lambda self, p: p.is_player and p != self.controller

        if v == 'player':
            criterias[i] = lambda self, p: p.is_player

        if v == 'creature or player':
            criterias[i] = (lambda self, p: p.is_player
                         or (p.is_creature and p.is_permanent))

        if v == 'spell':
            criterias[i] = lambda self, s: s.is_spell

        if v == 'instant or sorcery spell':
            criterias[i] = lambda self, s: s.is_spell and (s.is_instant or s.is_sorcery)

    return criterias


def parse_ability_costs(cost):
    _costs = cost.split(', ')
    costs = []

    if 'T' in _costs:
        costs.append("self.tap() and not self.is_summoning_sick")

    for itm in _costs:
        if mana_pattern.match(itm):
            costs.append("self.controller.pay('%s')" % itm)

        if re.match('[pP]ay [\dX]+ life', itm):
            costs.append("self.controller.pay(life=%s)" %
                         re.search('[\dX]+', itm).group(0))

        if itm == 'Sacrifice ~':
            costs.append("self.sacrifice()")

    # elif other costs

    costs = " and ".join(costs)
    return costs


def path_from_home(path):
    """
    Return a path that is relative to the "home" folder for the MTG engine data

    The location of the home folder is derived as follows:
    - if the MTG_ENGINE_HOME environment variable is set, its value is used;
    - otherwise, the home folder defaults to the current working directory

    NB: The given path MUST be a relative path

    :param path: The path to be made relative to the MTG engine's home
    :return: The same path, made relative to the engine's home folder
    """

    assert not os.path.isabs(path), f'Absolute paths are not supported by this function'

    engine_home = os.environ.get('MTG_ENGINE_HOME', '')  # If not set, home defaults to current working dir
    return os.path.join(engine_home, path)