import mock
import unittest
import time
# from copy import deepcopy

from MTG import game
from MTG import cards
from MTG import permanent
from MTG.exceptions import *
from MTG.utils import path_from_home

# test cases will fail if this is run
# inside setUpClass, b/c cards get set up multiple times
cards.setup_cards()

class TestGameBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = open('test_game_time.log', 'w')

    @classmethod
    def tearDownClass(cls):
        cls.f.close()

    def setUp(self):
        self.startTime = time.time()
        decks = [
            cards.read_deck(path_from_home('card_db/decks/mono_green.txt')),
            cards.read_deck(path_from_home('card_db/decks/mono_red.txt'))
        ]
        self.GAME = game.Game(decks, test=True)
        self.GAME.setup_game()
        self.player = self.GAME.players_list[0]
        self.opponent = self.GAME.players_list[1]
        
        self.player.tmp = False
        self.opponent.tmp = False
        self.player.hand.clear()  # start w/ no cards
        self.opponent.hand.clear()
        self.player.autoPayMana = True
        self.opponent.autoPayMana = True

    def tearDown(self):
        t = time.time() - self.startTime
        self.f.write("%s: %.3f\n" % (self.id(), t))


class TestGame(TestGameBase):
    def test_turn_do_nothing(self):
        with mock.patch('builtins.input', return_value=''):
            self.assertTrue(self.GAME.handle_turn())

    def test_game_over(self):
        """ Make sure that going to 0 life terminates the game"""
        with mock.patch('builtins.input', side_effect=['__self.life = 0', '']):
            with self.assertRaises(GameOverException):
                self.GAME.handle_turn()
                self.assertEqual(self.player.life, 0)
                self.assertTrue(self.player.lost)
                self.assertTrue(self.player not in self.GAME.players_list)

    def test_skip_priority(self):
        with mock.patch('builtins.input', return_value='s upkeep'):
            self.assertTrue(self.GAME.handle_turn())

    def test_mana_emptying(self):
        """Verify that both players' mana pool empties at end of phase"""
        with mock.patch('builtins.input', side_effect=[
                '__self.mana.add(mana.Mana.WHITE, 2)',
                '__self.mana.add(mana.Mana.RED, 3)', '',  # player 0
                '__self.mana.add(mana.Mana.BLUE, 2)', '',  # player 1
                '__self.tmp = self.mana.pool[mana.Mana.WHITE] '
            '+ self.mana.pool[mana.Mana.RED] == 0', '',  # p 0
                '__self.tmp = self.mana.pool[mana.Mana.BLUE] == 0', '',  # p 1
                's draw',
                's draw']):

            self.assertTrue(self.GAME.handle_turn())
            self.assertTrue(self.player.tmp)
            self.assertTrue(self.opponent.tmp)

    def test_drawing_cards(self):
        with mock.patch('builtins.input', side_effect=[
                '', '', '', '',
                '__self.draw(7)',
                '__self.tmp = len(self.hand) == 7',
                '__self.add_card_to_hand("Swamp")',
                '__self.draw(5)',
                '__self.tmp = self.tmp and len(self.hand) == 13',
                's draw',
                's draw',
                '']):

            self.assertTrue(self.GAME.handle_turn())
            self.assertTrue(self.player.tmp)
            self.assertEqual(len(self.player.hand), 7)  # discard down to 7 eot

    def test_discard(self):
        with mock.patch('builtins.input', side_effect=[
                '', '', '', '',
                '__self.draw(7)',
                '__self.draw(4)',
                '__self.discard(5)', '',  # auto discard
                's draw',
                's draw',
                '']):

            self.assertTrue(self.GAME.handle_turn())

            self.assertEqual(len(self.player.hand), 6)  # discard down to 7 eot
            self.assertEqual(len(self.player.graveyard), 5)

    def test_discard_down_to(self):
        """ Testing discarding DOWN TO 5 cards left in hand"""
        with mock.patch('builtins.input', side_effect=[
                '', '', '', '',
                '__self.draw(7)',
                '__self.draw(4)',
                '__self.discard(down_to = 5)', '0 2 3 5 8 1',
                's draw',
                's draw',
                '']):

            self.assertTrue(self.GAME.handle_turn())

            self.assertEqual(len(self.player.hand), 5)
            self.assertEqual(len(self.player.graveyard), 6)

    def test_discard_random(self):
        """ Testing random discard"""
        with mock.patch('builtins.input', side_effect=[
                '', '', '', '',
                '__self.draw(7)',
                '__self.draw(7)',
                '__self.discard(9, rand=True)',
                's draw',
                's draw',
                '']):

            self.assertTrue(self.GAME.handle_turn())

            self.assertEqual(len(self.player.hand), 5)
            self.assertEqual(len(self.player.graveyard), 9)

    def test_play_land(self):
        """Fetch an island from deck, play it, add blue mana.

        Validate that mana is correctly added & landPlayed count went up
        """

        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Island")',
                '', '', '', '',
                'p Island',
                'a 0',
                # use player.tmp as a placeholder
                '__self.tmp = self.mana.pool[mana.Mana.BLUE] == 1',
                's draw',
                's draw',
                '']):

            self.assertTrue(self.GAME.handle_turn())
            self.assertTrue(self.player.tmp)
            self.assertEqual(self.player.landPlayed, 1)

    def test_play_creature_basic_mana_payment(self):
        """Play a creature while having sufficient mana (automatic payment)

        Devouring Deep costs 2U
        """
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Devouring Deep")',
                '', '', '', '',
                '__self.mana.add(mana.Mana.BLUE, 3)',
                'p Devouring Deep', '',  # automatic mana payment
                's draw',
                's draw',
                '']):

            self.player.autoPayMana = False
            self.assertTrue(self.GAME.handle_turn())
            self.assertTrue(self.player.battlefield.get_card_by_name(
                            "Devouring Deep"))

    def test_play_creature_custom_mana_payment(self):
        """Play a creature while having sufficient mana (custom payment)"""
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Devouring Deep")',
                '', '', '', '',
                '__self.mana.add(mana.Mana.BLUE, 1)',
                '__self.mana.add(mana.Mana.RED, 1)',
                '__self.mana.add(mana.Mana.GREEN, 1)',
                'p Devouring Deep', 'RG',
                's draw',
                's draw',
                '']):

            self.player.autoPayMana = False
            self.assertTrue(self.GAME.handle_turn())
            self.assertTrue(
                self.player.battlefield.get_card_by_name("Devouring Deep"))

    def test_play_creature_over_three_turns(self):
        """ Fetch three lands, play them over three turns, tap for mana, play Devouring Deep

        Validate that creature uses the stack & is added to battlefield correctly
        Validate multiple turns pose no problem
        """

        with mock.patch('builtins.input', side_effect=[
                '__self.discard(-1)',
                '__self.add_card_to_hand("Island")',
                '__self.add_card_to_hand("Island")',
                '__self.add_card_to_hand("Plains")',
                '__self.add_card_to_hand("Devouring Deep")',
                '', '', '', '',
                'p Island',
                's precombat_main',
                's precombat_main',
                'p Plains',
                's precombat_main',
                's precombat_main',
                'p Island',
                'a 0', 'a 1', 'a 2',
                'p Devouring Deep',
                '__self.tmp = len(self.game.stack) == 1',
                '', '',
                's precombat_main',
                's precombat_main']):

            self.GAME.handle_turn()
            self.GAME.current_player = self.player
            self.GAME.handle_turn()
            self.GAME.current_player = self.player
            self.GAME.handle_turn()

            self.assertTrue(self.player.tmp)
            self.assertEqual(len(self.player.battlefield), 4)
            self.assertTrue(
                self.player.battlefield.get_card_by_name("Devouring Deep"))

    def test_summoning_sickness(self):
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Devouring Deep")',
                '', '', '', '',
                '__self.mana.add(mana.Mana.BLUE, 3)',
                'p Devouring Deep',
                '', '',  # letting it resolve
                '__self.tmp = not self.battlefield.get_card_by_name("Devouring Deep").can_attack()',
                's draw',
                's draw',
                '']):

            self.GAME.handle_turn()

            self.assertTrue(self.player.tmp)

    def test_attacking(self):
        with mock.patch('builtins.input', side_effect=[
                '__self.discard(-1)',
                '__self.add_card_to_hand("Devouring Deep")',
                '', '', '', '',
                '__self.mana.add(mana.Mana.BLUE, 3)',
                'p Devouring Deep', '',
                's draw',  # go to next turn
                's draw',
                '', '', '', '', '', '',  # skipping to declare_attackers
                '0',  # attacking w/ Devouring Deep
                      # check that it's tapped and attacking
                '__self.tmp = (self.battlefield.get_card_by_name("Devouring Deep")'
                            '.status.is_attacking == self.game.players_list[1]'
                            ' and self.battlefield.get_card_by_name("Devouring Deep")'
                            '.status.tapped)',
                's precombat_main',
                's precombat_main',
                '']):

            self.GAME.handle_turn()
            self.GAME.current_player = self.player
            self.GAME.handle_turn()

            self.assertTrue(self.player.tmp)
            self.assertTrue(self.player.battlefield.get_card_by_name(
                "Devouring Deep").status.tapped)
            self.assertFalse(self.player.battlefield.get_card_by_name(
                "Devouring Deep").in_combat)
            self.assertEqual(self.opponent.life, 19, "incorrect combat damage")

    @mock.patch.object(permanent.Permanent, 'take_damage')
    def test_blocking(self, mock_take_damage):
        """ single creature blocking single attacker; each do nonlethal damage"""

        with mock.patch('builtins.input', side_effect=[
                # p0
                '__self.discard(-1)', '__self.add_card_to_hand("Devouring Deep")', '',
                # p1
                '__self.discard(-1)', '__self.add_card_to_hand("Devouring Deep")', '',
                '', '',
                '__self.mana.add(mana.Mana.BLUE, 3)',  # player 0
                'p Devouring Deep', '', '', '',
                's precombat_main',  # go to next turn
                's precombat_main',
                '__self.mana.add(mana.Mana.BLUE, 3)',  # player 1's turn
                'p Devouring Deep', '', '', '',
                's precombat_main',  # go to next turn
                's precombat_main',
                '__self.battlefield[0].characteristics.power = 2',
                '', '', '', '',  # skipping to declare_attackers
                '0', '', '',  # attacking w/ Devouring Deep
                '0', '', '',  # blocking
                's precombat_main',
                's precombat_main',
                '']):

            self.GAME.handle_turn()
            self.GAME.handle_turn()
            self.GAME.handle_turn()
            self.assertEqual(mock_take_damage.call_count, 2)
            c1 = self.player.battlefield[0]
            c2 = self.opponent.battlefield[0]

            # unfortunately each instance of the patched method share the same call history
            # so we can't assert that, for example, c1.take_damage was called with source=c2 and vice versa
            mock_take_damage.assert_has_calls(
                [mock.call(c1, 2, True), mock.call(c2, 1, True)])

    def test_lethal_damage_in_combat(self):
        """ single creature blocking single attacker; both die"""
        with mock.patch('builtins.input', side_effect=[
                '__self.battlefield.add("Sewn-Eye Drake")', '',  # p0
                '__self.battlefield.add("Sewn-Eye Drake")', '',  # p1
                '', '',
                '', '', '', '',  # skipping to declare_attackers
                '0', '', '',  # attacking w/ Drake
                '0',  # blocking
                's precombat_main',
                's precombat_main',
                '']):

            self.GAME.handle_turn()
            self.assertEqual(len(self.player.graveyard), 1)
            self.assertEqual(self.player.life, 20)
            self.assertEqual(self.opponent.life, 20)

    def test_multiple_attacker(self):
        """ multiple attacker, one blocker. Damage goes to both player and creature."""
        with mock.patch('builtins.input', side_effect=[
                '__self.battlefield.add("Sewn-Eye Drake")',
                '__self.battlefield.add("Sewn-Eye Drake")',
                '__self.battlefield.add("Sewn-Eye Drake")', '',  # p0

                '__self.battlefield.add("Sewn-Eye Drake")', '',  # p1
                '', '',
                '', '', '', '',  # skipping to declare_attackers
                '0 1 2', '', '',  # attacking w/ everything
                '', '0', '',  # blocking the second drake
                's precombat_main',
                's precombat_main',
                '']):

            self.GAME.handle_turn()
            self.assertEqual(self.opponent.life, 14)
            self.assertEqual(len(self.player.graveyard), 1)
            self.assertEqual(len(self.opponent.graveyard), 1)

    def test_multiple_turns_alltogether(self):
        """multiple_attacker_multiple_blocker_custom_mana_pay"""
        with mock.patch('builtins.input', side_effect=[
                # p0
                '__self.discard(-1)', '__self.add_card_to_hand("Devouring Deep")',
                '__self.add_card_to_hand("Devouring Deep")',
                '__self.add_card_to_hand("Sewn-Eye Drake")',
                '', '', '', '',
                '__self.mana.add(mana.Mana.BLUE, 9)',  # player 0, main step
                '__self.mana.add(mana.Mana.BLACK, 1)',
                'p Devouring Deep', '', '', '',  # pay mana, letting it resolve
                'p Devouring Deep', '', '', '',
                # pay mana (choose hybrid & unrestricted), letting it resolve
                'p Sewn-Eye Drake', '', '', '', '',
                's precombat_main',
                's precombat_main',
                '0',  # attacking for 3 w/ haste

                '__self.discard(-1)', '__self.add_card_to_hand("Devouring Deep")',
                # player 1's turn, main step
                '__self.add_card_to_hand("Devouring Deep")',
                '__self.add_card_to_hand("Sewn-Eye Drake")',
                '__self.mana.add(mana.Mana.BLUE, 9)',
                '__self.mana.add(mana.Mana.BLACK, 1)',
                'p Devouring Deep', '', '', '',  # pay mana, letting it resolve
                'p Devouring Deep', '', '', '',
                'p Sewn-Eye Drake', '', '', '', '',
                's precombat_main',
                's precombat_main',
                # attacking w/ flyer, tries to block with Devouring Deep (but should fail due to flying), no blocks
                '0', '0', '',

                's precombat_main',  # go to next turn
                's precombat_main',
                '',  # no attacks

                's end_of_combat',  # go to next turn: player 1's attack
                's end_of_combat',
                '0 1 2',  # player 1 attacking with everything

                '0 1',  # Devouring Deep #1 gets blocked by both Devouring Deeps
                '',  # Devouring Deep #2 goes through
                '2',  # Drakes block each other

                # both drakes kill each other
                # double-block kills one of Player 1's Devouring Deep
                # player 0 takes 1 damage

                # player 1
                '__self.tmp = self.battlefield[0]'
                        '.status.damage_taken == 0'
                        ' and self.graveyard.get_card_by_name("Sewn-Eye Drake")'
                        ' and self.graveyard.get_card_by_name("Devouring Deep")',
                's draw',
                # player 0
            '__self.tmp = self.game.players_list[0].battlefield[0]'
                        '.status.damage_taken == 1'
                        ' and self.game.players_list[0].battlefield[1]'
                        '.status.damage_taken == 0'
                        ' and self.graveyard.get_card_by_name("Sewn-Eye Drake")',
                's draw']):

            self.player.autoPayMana = False
            self.opponent.autoPayMana = False
            self.GAME.handle_turn()
            self.GAME.handle_turn()
            self.GAME.handle_turn()
            self.GAME.handle_turn()
            self.assertEqual(len(self.player.battlefield), 2)
            self.assertEqual(len(self.opponent.battlefield), 1)
            self.assertEqual(self.player.life, 16)
            self.assertEqual(self.opponent.life, 17)
            self.assertTrue(self.player.tmp)
            self.assertTrue(self.opponent.tmp)

    # def test_trample(self):
    #     pass

    # def test_deathtouch(self):
    #     pass

    # def test_flying(self):
    #     pass

    # def test_lifelink(self):
    #     pass

    # def test_combat_damage_triggers(self):
    #     pass

    def test_haste(self):
        with mock.patch('builtins.input', side_effect=[
                '__self.battlefield.add("Sewn-Eye Drake")',
                '__self.battlefield.add("Devouring Deep")',
                '__self.tmp = self.battlefield[0].has_ability("Haste")'
            ' and not self.battlefield[1].has_ability("Haste")'
            ' and self.battlefield[0].can_attack()'
            ' and not self.battlefield[1].can_attack()',
                's upkeep',
                's upkeep',
                '']):  # no attack

            self.GAME.handle_turn()
            self.assertTrue(self.player.tmp)

    def test_lightning_strike(self):
        """Casts three lightning Strike in succession, using auto-pay mana; verify stack resolve order"""
        with mock.patch('builtins.input', side_effect=[
                '__self.battlefield.add("Sewn-Eye Drake")', '',
                '__self.battlefield.add("Devouring Deep")', '',  # player 1
                '__self.add_card_to_hand("Lightning Strike")',
                '__self.add_card_to_hand("Lightning Strike")',
                '__self.add_card_to_hand("Lightning Strike")',
                '__self.mana.add(mana.Mana.RED, 6)',
                'p Lightning Strike',
                'b 0',
                'p Lightning Strike',  # play another in response
                'ob 0',
                'p Lightning Strike',
                'op',
                '', '',  # resolve last one
                '__self.tmp = self.opponent.life == 17'
            ' and len(self.battlefield) == 1'
            ' and len(self.opponent.battlefield) == 1',
                '', '',
                '__self.tmp = self.tmp'
            ' and len(self.battlefield) == 1'
            ' and len(self.opponent.battlefield) == 0',
                '', '',
                '__self.tmp = self.tmp'
            ' and len(self.battlefield) == 0'
            # 3 lightning Strike & dead creature
            ' and len(self.graveyard) == 4',
                's upkeep',
                's upkeep']):  # no attack

            self.GAME.handle_turn()
            self.assertTrue(self.player.tmp)

    
    def test_triplicate_spirits(self):
        """Testing convoke, tokens, Spirit token has flying"""
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Triplicate Spirits")',
                '__self.add_card_to_hand("Triplicate Spirits")',
                '__self.add_card_to_hand("Triplicate Spirits")',
                '__self.battlefield.add("Soulmender")',
                '__self.battlefield.add("Child of Night")',
                's main', 's main', '__self.mana.add(mana.Mana.WHITE, 10)',
                'p Triplicate Spirits', '', '',  # convoke nothing
                '', '',  # it resolves
                '__self.tmp = self.mana.pool[mana.Mana.WHITE] == 4',
                'p Triplicate Spirits', '0 1', '',   # convoke 2
                '', '',  # it resolves
                'p Triplicate Spirits', '0 1 2 3 4 5', '',  # convoke 6
                '', '',  # it resolves
                's upkeep', 's upkeep',  # player 0's turn again
        ]):

            self.player.autoPayMana = False
            self.GAME.handle_turn()
            self.assertTrue(self.player.tmp)
            self.assertEqual(len(self.player.battlefield), 11)
            self.assertEqual(
                len([c for c in self.player.creatures if c.status.tapped]), 8)
            self.assertTrue(self.player.battlefield[-1].has_ability("Flying"))


    def test_squadron_hawk(self):
        """Testing search library, optional varibale number of cards"""
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Squadron Hawk")',
                '__self.library.add("Squadron Hawk")',
                '__self.library.add("Squadron Hawk")',
                '__self.library.add("Squadron Hawk")',
                '__self.tmp = [len(self.library)]',
                's main', 's main', '__self.mana.add(mana.Mana.WHITE, 10)',
                'p Squadron Hawk', '', '', '', '',
                '0 2',  # choose 2 out of the 3 squadron hawks in library
                '__self.tmp.extend([c.name == "Squadron Hawk" for c in self.hand[-2:]])',
                'p Squadron Hawk', '', '', '', '',
                '',     # don't search
                'p Squadron Hawk', '', '', '', '',
                '0',
                'p Squadron Hawk', '', '', '', '',
                '',
                '__self.tmp[0] = len(self.library) == __self.tmp[0] - 3',  # confirm we've removed the hawks
                's upkeep', 's upkeep'  # player 0's turn again
        ]):
            self.GAME.handle_turn()
            self.assertTrue(self.player.tmp)


    def test_target_fizzling(self):
        """Testing convoke, tokens, Spirit token has flying"""
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Peel from Reality")',
                '__self.add_card_to_hand("Peel from Reality")',
                '__self.add_card_to_hand("Ulcerate")',
                '__self.battlefield.add("Soulmender")',
                '__self.battlefield.add("Soulmender")', '',
                '__self.battlefield.add("Soulmender")', '',
                '__self.mana.add("UUUUB")',
                'p Ulcerate', 'ob 0',  # should fizzle and thus not lose life
                'p Peel from Reality', 'b 0', 'ob 0',  # should still resolve with one target illegal
                'p Peel from Reality', 'b 1', 'ob 0',
                's upkeep', 's upkeep'
        ]):
            self.player.autoDiscard = True
            self.opponent.autoDiscard = True
            self.GAME.handle_turn()
            self.assertEqual(len(self.player.battlefield), 0)  # everything should be bounced
            self.assertEqual(len(self.opponent.battlefield), 0)
            self.assertEqual(self.player.life, 20)
            self.assertEqual(len(self.player.graveyard), 3)  # 3 spells cast


    def test_indestructible(self):
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Ephemeral Shields")',
                '__self.battlefield.add("Soulmender")',
                '__self.battlefield.add("Soulmender")',
                'p Ephemeral Shields',
                'b 0',
                '0 1', '', '',  # use convoke to pay
                '__self.tmp = [self.battlefield[0].has_ability("Indestructible")]',
                '__self.battlefield[0].destroy()',
                '', '',
                '__self.tmp.append(len(self.battlefield == 2))',  # shouldn't be destroyed
                '__self.add_card_to_hand("Lightning Bolt")',
                'addmana',
                'p Lightning Bolt', 'b 0', '', '',  # damage shouldn't kill
                '__self.tmp.append(len(self.battlefield == 2))',
                '__self.add_card_to_hand("Ulcerate")',
                'p Ulcerate', 'b 0', '', '',    # however, lowering toughness below 0 should
                '__self.tmp.append(len(self.battlefield == 1))',
                's upkeep', 's upkeep'
        ]):
            self.GAME.handle_turn()
            self.assertTrue(all(self.player.tmp), msg=self.player.tmp)


    def test_intervening_if_triggers(self):
        with mock.patch('builtins.input', side_effect=[
                '__self.lose_life(5)',
                '__self.battlefield.add("Resolute Archangel")',
                '', '',  # let trigger resolve
                '__self.tmp = [self.life == 20]',  # reset life to 20
                '__self.battlefield[0].flicker()',
                '__self.tmp.append(len(self.game.stack) == 0)',  # shouldn't trigger since life !< 20
                '__self.lose_life(5)',
                '__self.battlefield[0].flicker()',
                '__self.tmp.append(len(self.game.stack) == 1)',  # should trigger
                '__self.gain_life(10)',
                '', '',
                '__self.tmp.append((self.life == 25))',  # triggeredAbility should fizzle and NOT reset life
                                                         # since now our life total is !< 20
               
                's upkeep', 's upkeep'
        ]):
            self.GAME.handle_turn()
            self.assertTrue(all(self.player.tmp), msg=self.player.tmp)


    def test_counterspells(self):
        with mock.patch('builtins.input', side_effect=[
                '__self.add_card_to_hand("Cancel")',
                '__self.add_card_to_hand("Cancel")',
                '__self.add_card_to_hand("Ajani\'s Pridemate")',
                's main', 's main', 'addmana',
                'p Ajani\'s Pridemate',
                'p Cancel',
                's 0',  # targetting Ajani's Pridemate
                '',     # opponent
                '__self.add_card_to_hand("Negate")',
                'addmana',
                'p Negate',  # opponent counterspelling our cancel
                's 1', '',
                'p Cancel',  # self, countering opponent's spell
                's 2', '',
                '',  # Let Cancel resolve, Negate should be countered now,
                '__self.tmp = [len(self.stack) == 2]',  # should be moved off stack
                '', '',  # Ajani's Pridemate should be countered now
                '__self.tmp.append(len(self.stack) == 0)',
                's upkeep', 's upkeep'
        ]):
            self.GAME.handle_turn()
            self.assertTrue(all(self.player.tmp), msg=self.player.tmp)



if __name__ == '__main__':
    unittest.main()
