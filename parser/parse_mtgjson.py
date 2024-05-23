import sys
import json
import pickle
import argparse

from MTG import static_abilities
from MTG.utils import path_from_home


def star_or_int(c):
    if c == '*':
        return c
    else:
        return int(c)


def run(format_id):

    with open(path_from_home(f'parser/formats/{format_id}.json')) as f:
        cards = json.load(f)
        card_list = []
        for _set in cards.values():
            card_list.extend(_set['cards'])

    fout = open(path_from_home(f"card_db/formats/{format_id}/cards.py"), "w")
    fout.write("from MTG import card\n"
               "from MTG import gameobject\n"
               "from MTG import cardtype\n"
               "from MTG import static_abilities\n"
               "from MTG import mana\n\n")

    name_to_id = {}

    for card in card_list:

        if card["name"] in name_to_id:  # already parsed card (ignore reprints)
            continue

        try:
            supertype = []
            subtype = []
            _abilities = []

            ID = f"c{card['id'].replace('-', '_')}"

            name = card["name"]
            characteristics = {'name': name}
            characteristics['text'] = card["oracle_text"] if "oracle_text" in card else '<missing>'
            characteristics['color'] = card["colorIdentity"] if "colorIdentity" in card else ''
            characteristics['mana_cost'] = (card["manaCost"].replace('{', '').replace('}', '')
                                            if "manaCost" in card else '')
            # types
            # NB: In line below, '—' is NOT a regular dash, is Unicode char U+2014
            parsed_types = card["type_line"].split('—')[0].strip().split(' ')

            if '—' in card["type_line"]:
                parsed_subtypes = card["type_line"].split('—')[1].strip()
            else:
                parsed_subtypes = ''

            card_types = []
            card_supertypes = []
            for type_token in parsed_types:

                if type_token in ['Basic']:
                    card_supertypes.append(type_token)
                elif type_token in ['Land', 'Creature', 'Instant']:
                    card_types.append(type_token)
                else:
                    assert False, f'Unknown type token: "{type_token}"'

            types = '[' + ', '.join(['cardtype.CardType.' + i.upper()
                                     for i in card_types]) + ']'
            supertype = ('['
                         + ', '.join(['cardtype.SuperType.' + i.upper()
                                      for i in card_supertypes])
                         + ']')

            characteristics["subtype"] = parsed_subtypes


            if 'Creature' in card["type_line"]:
                characteristics['power'], characteristics['toughness'] = star_or_int(
                    card["power"]), star_or_int(card["toughness"])

            # static abilities

            texts = characteristics['text'].replace(' ', '_')
            for ability in static_abilities.StaticAbilities._member_names_:
                if ability in texts or ',_' + ability.lower() in texts.lower():
                    _abilities.append(ability)

            if len(_abilities):
                _abilities = '[static_abilities.StaticAbilities.' + \
                    ', static_abilities.StaticAbilities.'.join(_abilities) + ']'

        except:
            print("\n\n")
            print(card)
            print(sys.exc_info())
            pass

        fout.write(
            """class {}(card.Card):
    "{}"
    def __init__(self):
        super({}, self).__init__(gameobject.Characteristics(**{}, supertype={}, types={}, abilities={}))

""".format(ID, name, ID, characteristics, supertype, types, _abilities))

        name_to_id[name] = ID
        
    with open(path_from_home(f"card_db/formats/{format_id}/name_to_id_dict.pkl"), "wb") as f:
        pickle.dump(name_to_id, f)

    fout.close()

    # try:
    #     card.find('text').text.replace(card.find('name').text, '<self>'))


if __name__ == '__main__':
    run("MTGRL")
