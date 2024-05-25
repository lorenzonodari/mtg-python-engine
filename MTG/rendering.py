from io import BytesIO

import pygame
import queue
import pickle

from MTG.game import Game
from MTG.card import Card
from MTG.player import Player
from MTG.zone import Stack

import requests
from requests import exceptions
from PIL import Image


IMAGES_DB = {}


def _load_card_image(image_url, resize=None):

    if image_url not in IMAGES_DB:

        # Fetch the image
        try:
            response = requests.get(image_url)

            if response.status_code == 200:

                print(f"[Info] Fetched card image: {image_url}")
                image = Image.open(BytesIO(response.content))
                IMAGES_DB[image_url] = image

            else:
                print(f'[Error] Could not load card image: {image_url}')
                IMAGES_DB[image_url] = None

        except exceptions.ConnectionError:
            print(f'[Exception] Could not load image {image_url}')
            IMAGES_DB[image_url] = None

    image = IMAGES_DB[image_url]

    if image is not None:

        if resize is not None:
            image = image.resize(resize)

        image_data = image.tobytes()
        image_dimensions = image.size
        image_screen = pygame.image.fromstring(image_data, image_dimensions, "RGB")

    else:
        image_screen = pygame.Surface(resize)

    return image_screen


def pygame_event_loop(screen: pygame.Surface, gamestates_queue: queue.Queue) -> None:

    clock = pygame.time.Clock()
    gamestate = gamestates_queue.get()

    running = True
    while running:

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((0, 0, 0))
        render_gamestate_frame(gamestate, screen)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def render_gamestate_frame(gamestate: Game, screen: pygame.Surface) -> None:

    row_h = screen.get_height() / 10

    # Divide the screen into 3 zones: player 1, stack, player 2
    player1_screen = screen.subsurface(pygame.Rect(0, 0, screen.get_width(), 4 * row_h))
    turn_screen = screen.subsurface(pygame.Rect(0, 4 * row_h, screen.get_width(), 2 * row_h))
    player2_screen = screen.subsurface(pygame.Rect(0, 6 * row_h, screen.get_width(), 4 * row_h))

    player1_screen.fill((255, 0, 0))
    turn_screen.fill((255, 255, 255))
    player2_screen.fill((0, 255, 0))

    render_player_state(gamestate.players_list[0], player1_screen)
    render_player_state(gamestate.players_list[1], player2_screen)
    render_turn_state(gamestate, turn_screen)


def render_player_state(player: Player, player_screen: pygame.Surface) -> None:

    player_status_str = f"Player {player.name} - Life: {player.life}"
    player_status = pygame.font.SysFont('serif', 32).render(player_status_str, True, (0, 0, 0))
    player_screen.blit(player_status, (0, 0))

    status_h = player_status.get_height()
    remaining_h = player_screen.get_height() - status_h
    row_h = remaining_h / 3  # 1 col Hand, 2 cols Battlefield (non-lands, lands)
    col_w = player_screen.get_width() / 7  # 1 col for deck, graveyard and exile, 6 for the rest of the battlefield/hand

    hand_subscreen = player_screen.subsurface(pygame.Rect(0, status_h, 6 * col_w, row_h))
    battlefield_subscreen = player_screen.subsurface(pygame.Rect(0, status_h + row_h, 6 * col_w, 2 * row_h))
    lge_subscreen = player_screen.subsurface(pygame.Rect(6 * col_w, status_h, col_w, remaining_h))  # Library, Graveyard, Exile

    hand_subscreen.fill((25, 25, 25))
    battlefield_subscreen.fill((50, 50, 50))
    lge_subscreen.fill((75, 75, 75))

    render_player_hand(player, hand_subscreen)
    render_player_battlefield(player, battlefield_subscreen)
    # TODO: Render player library, graveyard, exile


def render_player_hand(player: Player, hand_screen: pygame.Surface) -> None:

    num_cols = 15
    col_w = hand_screen.get_width() / num_cols
    screen_h = hand_screen.get_height()

    for i, card in enumerate(player.hand):

        if i == num_cols - 1:
            more_cards_str = f" + others"
            more_cards = pygame.font.SysFont('serif', 32).render(more_cards_str, True, (0, 0, 0))
            hand_screen.blit(more_cards, (i * col_w, 0))
            break

        card_subscreen = hand_screen.subsurface(pygame.Rect(i * col_w, 0, col_w, screen_h))

        card_subscreen.fill((int(255 / (i + 1)), int(255 / (i + 1)), int(255 / (i + 1))))

        render_card(card, card_subscreen)


def render_player_battlefield(player: Player, battlefield_screen: pygame) -> None:

    num_cols = 15
    screen_w = battlefield_screen.get_width()
    col_w = screen_w / num_cols
    row_h = battlefield_screen.get_height() / 2

    nonlands_subscreen = battlefield_screen.subsurface(pygame.Rect(0, 0, screen_w, row_h))
    lands_subscreen = battlefield_screen.subsurface(pygame.Rect(0, row_h, screen_w, row_h))

    nonlands_subscreen.fill((100, 100, 100))
    lands_subscreen.fill((125, 125, 125))

    nonlands_i = 0  # Column indexes to be occupied next
    lands_i = 0     # by nonlands and lands respectively
    for i, permanent in enumerate(player.battlefield):

        if permanent.is_land:
            card_y0 = row_h
            card_x0 = lands_i * col_w
            lands_i += 1
        else:
            card_y0 = 0
            card_x0 = nonlands_i * col_w
            nonlands_i += 1

        card_subscreen = battlefield_screen.subsurface(pygame.Rect(card_x0, card_y0, col_w, row_h))
        card = permanent.original_card
        render_card(card, card_subscreen)

        # TODO: Render status
        # TODO: Render modifications


def render_card(card: Card, card_screen: pygame.Surface) -> None:

    card_img_url = card.characteristics.image_url
    card_img_screen = _load_card_image(card_img_url, resize=(card_screen.get_width(), card_screen.get_height()))

    if card_screen is not None:
        rendered_card = card_img_screen
    else:
        rendered_card = pygame.font.SysFont('serif', 8).render(card_img_url, True, (0, 0, 0))

    card_screen.blit(rendered_card, (0, 0))


def render_turn_state(game: Game, turn_screen: pygame.Surface) -> None:

    screen_h = turn_screen.get_height()
    col_w = turn_screen.get_width() / 2

    stack_subscreen = turn_screen.subsurface(pygame.Rect(0, 0, col_w, screen_h))
    info_subscreen = turn_screen.subsurface(pygame.Rect(col_w, 0, col_w, screen_h))

    stack_subscreen.fill((200, 200, 225))
    info_subscreen.fill((225, 225, 225))

    render_stack_state(game.stack, stack_subscreen)
    render_turn_info(game, info_subscreen)


def render_stack_state(stack: Stack, stack_screen: pygame.Surface) -> None:

    stack_name = pygame.font.SysFont('serif', 32).render("Stack", True, (0, 0, 0))
    stack_screen.blit(stack_name, (0, 0))


def render_turn_info(game: Game, turn_screen: pygame.Surface) -> None:

    info = pygame.font.SysFont('serif', 32).render("Info", True, (0, 0, 0))
    turn_screen.blit(info, (0, 0))

    turn_number = f"Turn #{game.turn_num}"

    upper_player = game.players_list[0]
    if game.current_player is upper_player:
        current_player = "Turn player: /\\"
    else:
        current_player = "Turn player: \\/"

    if not game.passed_priority:
        priority = "Priority: /\\"
    else:
        priority = "Priority: \\/"

    turn_priority_str = " - ".join((turn_number, current_player, priority))

    turn_priority_info = pygame.font.SysFont('serif', 24).render(turn_priority_str, True, (0, 0, 0))
    turn_screen.blit(turn_priority_info, (0, info.get_height()))


if __name__ == "__main__":

    with open('test.pkl', 'rb') as pickled_game:
        game = pickle.load(pickled_game)

    queue = queue.Queue(maxsize=1)
    queue.put_nowait(game)

    pygame.init()
    screen = pygame.display.set_mode((1440, 810))
    pygame_event_loop(screen, queue)

