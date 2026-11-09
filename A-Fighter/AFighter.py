
import os
import math
import random
import pygame

# sound settings must be set before pygame.init()
pygame.mixer.pre_init(48000, -16, 2, 1024)
pygame.init()
pygame.mixer.set_num_channels(32)

from class1 import (Fighter, button, text_button, power_up, FX, CPUController,
                    MAX_HEALTH, ATTACKS, FPS)

# ------------------------------------------------------------------ window
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
BAR_WIDTH = int(SCREEN_WIDTH // 2.6)
BAR_HEIGHT = 30
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption('Afighter')
canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))   # everything is drawn here, then shaken onto the screen
clock = pygame.time.Clock()

# colours
RED = (255, 60, 60)
YELLOW = (255, 220, 40)
WHITE = (255, 255, 255)

# default settings (changeable from the Options screen)
DEFAULT_MODE = 'pvp'            # 'pvp' = two players, 'cpu' = you vs the computer
DEFAULT_DIFFICULTY = 'normal'   # 'easy' / 'normal' / 'hard'
settings = {'mode': DEFAULT_MODE, 'difficulty': DEFAULT_DIFFICULTY, 'rounds': 2, 'time': 60}

INTRO_STEP = 60                 # frames per countdown number
ROUND_OVER_FRAMES = 190         # how long the round-end screen lasts
POWER_UP_INTERVAL = 240         # frames between power-up spawns


# ------------------------------------------------------------------ asset helpers
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def asset(*parts):
    """Find a file inside the Assets folder (works with or without a file extension)."""
    for root in ('Assets', 'assets'):
        path = os.path.join(BASE_DIR, root, *parts)
        if os.path.exists(path):
            return path
        for ext in ('.png', '.jpg', '.wav', '.mp3', '.ogg', '.ttf', '.otf'):
            if os.path.exists(path + ext):
                return path + ext
    return os.path.join(BASE_DIR, 'Assets', *parts)


def load_image(*parts):
    path = asset(*parts)
    try:
        return pygame.image.load(path).convert_alpha()
    except (FileNotFoundError, pygame.error) as err:
        raise SystemExit('Could not load image: %s\n%s' % (path, err))


def load_font(parts, size):
    try:
        return pygame.font.Font(asset(*parts), size)
    except (FileNotFoundError, OSError, pygame.error):
        return pygame.font.SysFont('arialblack', int(size * 0.8))


class NullSound():
    """Stand-in used when a sound file is missing, so the game still runs."""
    def play(self, *args, **kwargs):
        pass

    def set_volume(self, *args):
        pass


def load_sound(*parts):
    path = asset(*parts)
    try:
        return pygame.mixer.Sound(path)
    except (FileNotFoundError, pygame.error) as err:
        print('[missing sound]', path, '-', err)
        return NullSound()


def split_frames(sheet, count, size=(200, 200)):
    frame_w = sheet.get_width() // count
    frame_h = sheet.get_height()
    frames = []
    for i in range(count):
        frame = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
        frame.blit(sheet, (0, 0), pygame.Rect(i * frame_w, 0, frame_w, frame_h))
        frames.append(pygame.transform.scale(frame, size))
    return frames


# ------------------------------------------------------------------ fonts
FONT_PATH = ('Menu and settings', 'turok')
count_font = load_font(FONT_PATH, 90)
big_font = load_font(FONT_PATH, 70)
timer_font = load_font(FONT_PATH, 44)
score_font = load_font(FONT_PATH, 30)
small_font = load_font(FONT_PATH, 24)
tiny_font = load_font(FONT_PATH, 17)
menu_font = load_font(FONT_PATH, 26)


# ------------------------------------------------------------------ music + sounds
try:
    pygame.mixer.music.load(asset('Music and sfx', 'bg_music'))
    pygame.mixer.music.set_volume(0.2)
    pygame.mixer.music.play(-1, 0.0, 5000)
except (FileNotFoundError, pygame.error) as err:
    print('[music not loaded]', err)

Ready = load_sound('Music and sfx', 'Ready')

S_walking = load_sound('S_sfx', 'S_walking')
S_walking.set_volume(0.5)
M_walking = load_sound('M_sfx', 'M_walking')
M_walking.set_volume(0.5)

# event name -> sound, for each fighter (the Fighter class reports events like 'hit' or 'attack1')
SOUNDS = {
    1: {
        'step': S_walking,
        'attack1': load_sound('S_sfx', 'S_attack'),
        'attack2': load_sound('S_sfx', 'S_attack2'),
        'attack3': load_sound('S_sfx', 'S_attack3'),
        'hit': load_sound('S_sfx', 'S_takehit'),
        'block1': load_sound('S_sfx', 'S_block_break1'),
        'block2': load_sound('S_sfx', 'S_block_break2'),
        'block3': load_sound('S_sfx', 'S_block_break3'),
        'death': load_sound('S_sfx', 'S_death'),
    },
    2: {
        'step': M_walking,
        'jump': load_sound('M_sfx', 'M_jump'),
        'attack1': load_sound('M_sfx', 'M_attack1'),
        'attack2': load_sound('M_sfx', 'M_attack2'),
        'attack3': load_sound('M_sfx', 'M_attack3'),
        'hit': load_sound('M_sfx', 'M_takehit'),
        'block1': load_sound('M_sfx', 'M_block_break_1'),
        'block2': load_sound('M_sfx', 'M_block_break_2'),
        'block3': load_sound('M_sfx', 'M_block_break_3'),
        'death': load_sound('M_sfx', 'M_death'),
    },
}

# each fighter gets their own channels so sounds don't cut each other off
CHANNELS = {
    1: {'attack': pygame.mixer.Channel(0), 'hit': pygame.mixer.Channel(1), 'step': pygame.mixer.Channel(2)},
    2: {'attack': pygame.mixer.Channel(3), 'hit': pygame.mixer.Channel(4), 'step': pygame.mixer.Channel(5)},
}
ui_channel = pygame.mixer.Channel(6)
CHANNEL_FOR_EVENT = {'attack1': 'attack', 'attack2': 'attack', 'attack3': 'attack',
                     'hit': 'hit', 'block1': 'hit', 'block2': 'hit', 'block3': 'hit',
                     'death': 'hit', 'step': 'step'}


def play_events(fighter):
    for event in fighter.drain_events():
        sound = SOUNDS[fighter.player].get(event)
        if sound is None or isinstance(sound, NullSound):
            continue
        channel_name = CHANNEL_FOR_EVENT.get(event)
        if channel_name is None:
            sound.play()
            continue
        channel = CHANNELS[fighter.player][channel_name]
        if event == 'step' and channel.get_busy():
            continue
        channel.play(sound)


# ------------------------------------------------------------------ images
bg_image = load_image('Menu and settings', 'bg')
bg_scaled = pygame.transform.scale(bg_image, (SCREEN_WIDTH, SCREEN_HEIGHT)).convert()
victory_img = load_image('Menu and settings', 'Victory')

# skeleton
S_idle = load_image('Skeleton animations', 'Idle')
S_walk = load_image('Skeleton animations', 'Walk')
S_attack1_img = load_image('Skeleton animations', 'Attack1')
S_attack2_img = load_image('Skeleton animations', 'Attack2')
S_attack3_img = load_image('Skeleton animations', 'Attack3')
S_block_img = load_image('Skeleton animations', 'Block')
S_takehit = load_image('Skeleton animations', 'Take Hit')
S_death = load_image('Skeleton animations', 'Death')
fighter_1_sprites = [S_idle, S_walk, S_idle, S_attack1_img, S_attack2_img, S_attack3_img,
                     S_block_img, S_takehit, S_death]

# mushroom
M_idle = load_image('Mushroom animations', 'Idle')
M_walk = load_image('Mushroom animations', 'Run')
M_attack1_img = load_image('Mushroom animations', 'Attack1')
M_attack2_img = load_image('Mushroom animations', 'Attack2')
M_attack3_img = load_image('Mushroom animations', 'Attack3')
M_jump_img = load_image('Mushroom animations', 'Jump')
M_block_img = load_image('Mushroom animations', 'Block')
M_takehit = load_image('Mushroom animations', 'Take Hit')
M_death = load_image('Mushroom animations', 'Death')
fighter_2_sprites = [M_idle, M_walk, M_jump_img, M_attack1_img, M_attack2_img, M_attack3_img,
                     M_block_img, M_takehit, M_death]

Fighter_1_projectile_frames = split_frames(load_image('Skeleton animations', 'Sword_sprite'), 8)
Fighter_2_projectile_frames = split_frames(load_image('Mushroom animations', 'Projectile_sprite'), 8)

start_img = load_image('Menu and settings', 'start_btn')
exit_img = load_image('Menu and settings', 'exit_btn')
opt_img = load_image('Menu and settings', 'opt_btn')
save_img = load_image('Menu and settings', 'save_btn')

# fighter data: [sprite size, scale, offset]
SKELETON_DATA = [150, 3, [50, 50]]
SKELETON_ANIMATION_STEPS = [4, 4, 4, 8, 8, 8, 4, 4, 4]
MUSHROOM_DATA = [150, 3, [50, 50]]
MUSHROOM_ANIMATION_STEPS = [4, 4, 4, 8, 8, 11, 4, 4, 4]


def make_vignette(w, h, strength=170, depth=100):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(depth):
        alpha = int(strength * (1 - i / depth) ** 2)
        pygame.draw.rect(surf, (0, 0, 0, alpha), (i, i, w - 2 * i, h - 2 * i), 1)
    return surf


vignette = make_vignette(SCREEN_WIDTH, SCREEN_HEIGHT)
dim_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
dim_overlay.fill((0, 0, 0, 165))

# ------------------------------------------------------------------ menu buttons
start_button = button(350, 100, start_img, 2)
opt_button = button(310, 300, opt_img, 2)
exit_button = button(360, 500, exit_img, 2)
save_button = button(360, 100, save_img, 2)
save_button.rect.midbottom = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 20)    # back button sits at the bottom of Options

BTN_W = 440
mode_button = text_button((SCREEN_WIDTH - BTN_W) // 2, 100, BTN_W, 46, menu_font)
difficulty_button = text_button((SCREEN_WIDTH - BTN_W) // 2, 156, BTN_W, 46, menu_font)
rounds_button = text_button((SCREEN_WIDTH - BTN_W) // 2, 212, BTN_W, 46, menu_font)
time_button = text_button((SCREEN_WIDTH - BTN_W) // 2, 268, BTN_W, 46, menu_font)
restart_button = text_button(SCREEN_WIDTH - 250, SCREEN_HEIGHT - 80, 230, 46, menu_font)

fx = FX(small_font, score_font)


# ------------------------------------------------------------------ drawing helpers
def draw_text(text, font, color, x, y, center=False, right=False, shadow=True):
    img = font.render(text, True, color)
    if center:
        x -= img.get_width() // 2
    elif right:
        x -= img.get_width()
    if shadow:
        canvas.blit(font.render(text, True, (0, 0, 0)), (x + 2, y + 2))
    canvas.blit(img, (x, y))


def draw_pop_text(text, font, color, y, age, pop=1.5, settle=10):
    """Big centred text that 'pops' in and settles."""
    img = font.render(text, True, color)
    shadow = font.render(text, True, (0, 0, 0))
    scale = 1 + (pop - 1) * max(0.0, 1 - age / settle)
    if scale != 1:
        img = pygame.transform.rotozoom(img, 0, scale)
        shadow = pygame.transform.rotozoom(shadow, 0, scale)
    cx = SCREEN_WIDTH // 2
    canvas.blit(shadow, shadow.get_rect(center=(cx + 3, y + 3)))
    canvas.blit(img, img.get_rect(center=(cx, y)))


def draw_health_bar(f, x, mirror):
    y, w, h = 20, 400, 30
    pygame.draw.rect(canvas, (15, 15, 20), (x - 4, y - 4, w + 8, h + 8), border_radius=7)
    pygame.draw.rect(canvas, (110, 25, 25), (x, y, w, h), border_radius=5)       # empty part (red)

    def segment(fraction, color):
        seg_w = int(w * max(0.0, min(1.0, fraction)))
        if seg_w <= 0:
            return
        rect = pygame.Rect(x + (w - seg_w if mirror else 0), y, seg_w, h)
        pygame.draw.rect(canvas, color, rect, border_radius=5)
        light = tuple(min(255, c + 70) for c in color)
        pygame.draw.rect(canvas, light, (rect.x + 3, rect.y + 3, max(0, rect.w - 6), 7), border_radius=3)

    segment(f.lag_health / MAX_HEALTH, (255, 255, 255))                          # white damage trail
    low = f.health / MAX_HEALTH < 0.3
    segment(f.health / MAX_HEALTH, (255, 90, 60) if low and (frame_count // 8) % 2 == 0 else YELLOW)
    pygame.draw.rect(canvas, WHITE, (x - 2, y - 2, w + 4, h + 4), 2, border_radius=6)
    if mirror:
        draw_text(str(f.health), small_font, WHITE, x + 10, y + 1)
    else:
        draw_text(str(f.health), small_font, WHITE, x + w - 10, y + 1, right=True)


def draw_mini_bar(x, y, w, fraction, color, label, ready_color=None):
    fraction = max(0.0, min(1.0, fraction))
    draw_text(label, tiny_font, WHITE if fraction >= 1 else (170, 170, 170), x, y, shadow=False)
    pygame.draw.rect(canvas, (20, 20, 30), (x, y + 18, w, 7), border_radius=3)
    col = (ready_color or color) if fraction >= 1 else color
    if fraction > 0:
        pygame.draw.rect(canvas, col, (x, y + 18, int(w * fraction), 7), border_radius=3)
    pygame.draw.rect(canvas, (200, 200, 210), (x, y + 18, w, 7), 1, border_radius=3)


def draw_charge_bar(f, x, y, key_label):
    base = pygame.Rect(x, y, BAR_WIDTH, BAR_HEIGHT)
    pygame.draw.rect(canvas, (25, 25, 40), base, border_radius=8)
    width = int(BAR_WIDTH * f.attack_charge / f.max_charge)
    full = f.attack_charge >= f.max_charge
    if width > 0:
        if full:
            pulse = 0.5 + 0.5 * math.sin(frame_count * 0.25)
            color = (int(70 + 150 * pulse), int(130 + 100 * pulse), 255)
        else:
            color = (40, 110, 255)
        pygame.draw.rect(canvas, color, (x, y, width, BAR_HEIGHT), border_radius=8)
        light = tuple(min(255, c + 70) for c in color)
        pygame.draw.rect(canvas, light, (x + 4, y + 4, max(0, width - 8), 7), border_radius=4)
    pygame.draw.rect(canvas, WHITE, base, 2, border_radius=8)
    if full:
        label = 'SPECIAL READY' + ('' if key_label is None else ' - press ' + key_label)
    else:
        label = 'SPECIAL'
    draw_text(label, tiny_font, WHITE, x + BAR_WIDTH // 2, y + 5, center=True)


def draw_hud():
    # health bars
    draw_health_bar(f1, 20, False)
    draw_health_bar(f2, SCREEN_WIDTH - 420, True)

    # names
    draw_text('P1  ' + f1.name, small_font, WHITE, 20, 56)
    tag = 'CPU' if f2.controller is not None else 'P2'
    draw_text(f2.name + '  ' + tag, small_font, WHITE, SCREEN_WIDTH - 20, 56, right=True)

    # round-win pips
    for i in range(settings['rounds']):
        pygame.draw.circle(canvas, YELLOW if score[0] > i else (60, 60, 70), (408 - i * 24, 68), 8)
        pygame.draw.circle(canvas, WHITE, (408 - i * 24, 68), 8, 2)
        pygame.draw.circle(canvas, YELLOW if score[1] > i else (60, 60, 70), (SCREEN_WIDTH - 408 + i * 24, 68), 8)
        pygame.draw.circle(canvas, WHITE, (SCREEN_WIDTH - 408 + i * 24, 68), 8, 2)

    # timer
    pygame.draw.rect(canvas, (15, 15, 20), (438, 14, 124, 56), border_radius=10)
    pygame.draw.rect(canvas, WHITE, (438, 14, 124, 56), 2, border_radius=10)
    if settings['time'] > 0:
        secs = max(0, math.ceil(time_left / FPS))
        color = RED if secs <= 10 and (frame_count // 15) % 2 == 0 else WHITE
        draw_text(str(secs), timer_font, color, 500, 20, center=True)
    else:
        draw_text('--', timer_font, WHITE, 500, 20, center=True)

    # small cooldown bars: heavy attack, shield, speed boost
    for f, left in ((f1, True), (f2, False)):
        heavy = 0.0 if f.attack2_active else 1 - f.attack2_cooldown / ATTACKS['attack2']['cooldown']
        shield = 1.0 if f.can_block else 1 - f.block_cooldown / max(1, f.block_lock_total)
        xs = [20, 150, 280] if left else [SCREEN_WIDTH - 140, SCREEN_WIDTH - 270, SCREEN_WIDTH - 400]
        draw_mini_bar(xs[0], 84, 120, heavy, (170, 110, 60), 'HEAVY', (255, 160, 80))
        draw_mini_bar(xs[1], 84, 120, shield, (70, 110, 150), 'SHIELD', (120, 210, 255))
        if f.speed_boost > 0:
            draw_mini_bar(xs[2], 84, 120, f.speed_boost_timer / f.speed_boost_max, (0, 200, 0), 'SPEED')
        if f.combo_count >= 2 and f.combo_timer > 0:
            text = '%d HIT COMBO!' % f.combo_count
            if left:
                draw_text(text, small_font, YELLOW, 20, 118)
            else:
                draw_text(text, small_font, YELLOW, SCREEN_WIDTH - 20, 118, right=True)

    # special bars at the bottom
    draw_charge_bar(f1, 75, SCREEN_HEIGHT - 40, 'F')
    draw_charge_bar(f2, SCREEN_WIDTH - 425, SCREEN_HEIGHT - 40, None if f2.controller is not None else 'H')


# ------------------------------------------------------------------ game state
score = [0, 0]
round_number = 1
f1 = f2 = None
intro_count = 4
intro_timer = INTRO_STEP
fight_banner = 0
round_over = False
round_over_timer = 0
round_winner = 0
round_reason = 'K.O.'
match_over = False
match_winner = 0
time_left = 0
current_power_up = None
power_up_spawn_timer = 0
frame_count = 0

game_paused = True
menu_state = 'main'
match_in_progress = False
settings_dirty = False
ui_lock = False
run = True


def create_fighters():
    fx.clear()
    controller = CPUController(settings['difficulty']) if settings['mode'] == 'cpu' else None
    fighter_1 = Fighter(1, 200, 500, False, SKELETON_DATA, fighter_1_sprites, SKELETON_ANIMATION_STEPS,
                        Fighter_1_projectile_frames, fx=fx, name='SKELETON')
    fighter_2 = Fighter(2, 700, 500, True, MUSHROOM_DATA, fighter_2_sprites, MUSHROOM_ANIMATION_STEPS,
                        Fighter_2_projectile_frames, fx=fx, name='MUSHROOM', controller=controller)
    if controller is not None:
        controller.bind(fighter_2, fighter_1)
    return fighter_1, fighter_2


def new_round():
    global f1, f2, intro_count, intro_timer, fight_banner, round_over, round_over_timer
    global time_left, current_power_up, power_up_spawn_timer
    f1, f2 = create_fighters()
    intro_count = 4
    intro_timer = INTRO_STEP
    fight_banner = 0
    round_over = False
    round_over_timer = 0
    time_left = settings['time'] * FPS
    current_power_up = None
    power_up_spawn_timer = 0


def new_match():
    global round_number, match_over, match_in_progress, settings_dirty
    score[0] = score[1] = 0
    round_number = 1
    match_over = False
    match_in_progress = True
    settings_dirty = False
    new_round()


def resume_or_start():
    global game_paused
    if not match_in_progress or settings_dirty:
        new_match()
    game_paused = False


def set_menu(state):
    global menu_state, ui_lock
    menu_state = state
    ui_lock = True          # ignore the mouse until the button is released


def go_to_menu():
    global match_in_progress, game_paused
    match_in_progress = False
    game_paused = True
    set_menu('main')


def cycle(options, value):
    return options[(options.index(value) + 1) % len(options)]


new_round()      # fighters exist from the start so the menu has something behind it


# ------------------------------------------------------------------ per-frame game logic
def update_game():
    global intro_count, intro_timer, fight_banner, round_over, round_over_timer, round_winner
    global round_reason, match_over, match_winner, time_left, current_power_up
    global power_up_spawn_timer, round_number

    frozen = fx.hitstop > 0          # hit-stop: freeze everything for a few frames on a big hit
    fx.update(frozen)
    if frozen:
        fx.hitstop -= 1
        return

    locked = intro_count > 0 or round_over or match_over

    # countdown
    if intro_count > 0:
        intro_timer -= 1
        if intro_timer <= 0:
            intro_count -= 1
            intro_timer = INTRO_STEP
            if intro_count in (3, 2, 1) and not isinstance(Ready, NullSound):
                ui_channel.play(Ready)
            if intro_count == 0:
                fight_banner = 55
    elif fight_banner > 0:
        fight_banner -= 1

    # fighters
    f1.move(SCREEN_WIDTH, SCREEN_HEIGHT, canvas, f2, locked)
    f2.move(SCREEN_WIDTH, SCREEN_HEIGHT, canvas, f1, locked)
    order = [(f1, f2), (f2, f1)]
    random.shuffle(order)            # fair when both land a hit on the same frame
    for fighter, other in order:
        fighter.update(canvas, other, SCREEN_WIDTH)
    play_events(f1)
    play_events(f2)

    if locked:
        pass
    else:
        if settings['time'] > 0:
            time_left -= 1

        # power-ups
        if current_power_up is None or not current_power_up.active:
            power_up_spawn_timer += 1
            if power_up_spawn_timer >= POWER_UP_INTERVAL:
                power_up_spawn_timer = 0
                current_power_up = power_up(random.choice(['health', 'speed', 'charge']),
                                            screen_width=SCREEN_WIDTH)
        else:
            rect = current_power_up.update()
            if current_power_up.off_screen():
                current_power_up.active = False
            else:
                for fighter in (f1, f2):
                    if fighter.alive and fighter.rect.colliderect(rect):
                        current_power_up.apply_effect(fighter, fx)
                        break

    # round end
    if not round_over and not match_over and intro_count == 0:
        time_up = settings['time'] > 0 and time_left <= 0
        if not f1.alive or not f2.alive or time_up:
            if not f1.alive and not f2.alive:
                round_winner = 0
            elif not f1.alive:
                round_winner = 2
            elif not f2.alive:
                round_winner = 1
            else:
                round_winner = 1 if f1.health > f2.health else 2 if f2.health > f1.health else 0
            round_reason = 'K.O.' if (not f1.alive or not f2.alive) else 'TIME!'
            if round_winner:
                score[round_winner - 1] += 1
            round_over = True
            round_over_timer = 0
            if round_reason == 'TIME!':
                fx.shake(8)

    if round_over and not match_over:
        round_over_timer += 1
        if round_over_timer >= ROUND_OVER_FRAMES:
            if max(score) >= settings['rounds']:
                match_over = True
                match_winner = 1 if score[0] > score[1] else 2
            else:
                round_number += 1
                new_round()


# ------------------------------------------------------------------ drawing the game
def draw_game():
    canvas.blit(bg_scaled, (0, 0))
    if current_power_up is not None and current_power_up.active:
        current_power_up.draw(canvas)
    for fighter in sorted((f1, f2), key=lambda f: f.alive):     # dead fighter is drawn underneath
        fighter.draw(canvas)
    f1.draw_projectile(canvas)
    f2.draw_projectile(canvas)
    fx.draw(canvas)
    canvas.blit(vignette, (0, 0))
    draw_hud()

    # countdown / FIGHT banner
    if intro_count > 0:
        age = INTRO_STEP - intro_timer
        if intro_count == 4:
            final = settings['rounds'] > 1 and score[0] == score[1] == settings['rounds'] - 1
            draw_pop_text('FINAL ROUND' if final else 'ROUND %d' % round_number, count_font, WHITE,
                          SCREEN_HEIGHT // 3, age)
        else:
            draw_pop_text(str(intro_count), count_font, RED, SCREEN_HEIGHT // 3, age)
    elif fight_banner > 0:
        draw_pop_text('FIGHT!', count_font, YELLOW, SCREEN_HEIGHT // 3, 55 - fight_banner)

    # round over
    if round_over and not match_over:
        if round_over_timer < 70:
            draw_pop_text(round_reason, count_font, RED, SCREEN_HEIGHT // 3, round_over_timer)
        else:
            canvas.blit(victory_img, ((SCREEN_WIDTH - victory_img.get_width()) // 2, 150))
            if round_winner == 0:
                msg = 'DRAW - REPLAY ROUND'
            else:
                msg = '%s WINS THE ROUND' % (f1.name if round_winner == 1 else f2.name)
            draw_text(msg, score_font, WHITE, SCREEN_WIDTH // 2, 160 + victory_img.get_height(), center=True)

    # match over
    if match_over:
        canvas.blit(dim_overlay, (0, 0))
        winner = f1 if match_winner == 1 else f2
        draw_text('%s WINS THE MATCH!' % winner.name, big_font, YELLOW, SCREEN_WIDTH // 2, 230, center=True)
        draw_text('%d  -  %d' % (score[0], score[1]), count_font, WHITE, SCREEN_WIDTH // 2, 330, center=True)
        draw_text('ENTER: rematch        ESC: main menu', score_font, WHITE, SCREEN_WIDTH // 2, 470, center=True)


# ------------------------------------------------------------------ menus
P1_KEYS = ['A / D  -  move', 'W  -  jump (press twice to double jump)', 'R  -  light attack',
           'T  -  heavy attack', 'F  -  special (when the bar is full)', 'V  -  hold to block']
P2_KEYS = ['J / L  -  move', 'I  -  jump (press twice to double jump)', 'U  -  light attack',
           'Y  -  heavy attack', 'H  -  special (when the bar is full)', 'B  -  hold to block']


def mode_text():
    if settings['mode'] == 'pvp':
        return '2 Players'
    return 'vs CPU (%s)' % settings['difficulty'].title()


def draw_menu():
    global run, settings_dirty, ui_lock, game_paused
    if ui_lock and not pygame.mouse.get_pressed()[0]:
        ui_lock = False

    def clicked(widget, *args):
        return widget.draw(canvas, *args) and not ui_lock

    if match_in_progress:
        draw_game()                                  # show the paused match behind the menu
    else:
        canvas.blit(bg_scaled, (0, 0))
    canvas.blit(dim_overlay, (0, 0))

    if menu_state == 'main':
        draw_text('PAUSED' if match_in_progress else 'A-FIGHTER', big_font, WHITE,
                  SCREEN_WIDTH // 2, 12, center=True)
        if clicked(start_button):
            resume_or_start()
        if clicked(opt_button):
            set_menu('options')
        if clicked(exit_button):
            run = False
        if match_in_progress and clicked(restart_button, 'Restart match'):
            new_match()
            game_paused = False
        draw_text('Mode: %s   |   SPACE / ESC: pause' % mode_text(), small_font, WHITE,
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 38, center=True)
    else:
        draw_text('OPTIONS', big_font, WHITE, SCREEN_WIDTH // 2, 12, center=True)
        if clicked(mode_button, 'Mode: ' + ('2 Players' if settings['mode'] == 'pvp' else 'vs CPU')):
            settings['mode'] = cycle(['pvp', 'cpu'], settings['mode'])
            settings_dirty = True
        if clicked(difficulty_button, 'CPU difficulty: ' + settings['difficulty'].title()):
            settings['difficulty'] = cycle(['easy', 'normal', 'hard'], settings['difficulty'])
            settings_dirty = True
        if clicked(rounds_button, 'First to %d round%s' % (settings['rounds'], '' if settings['rounds'] == 1 else 's')):
            settings['rounds'] = cycle([1, 2, 3], settings['rounds'])
            settings_dirty = True
        if clicked(time_button, 'Round timer: ' + ('off' if settings['time'] == 0 else '%d seconds' % settings['time'])):
            settings['time'] = cycle([0, 30, 60, 99], settings['time'])
            settings_dirty = True
        if match_in_progress:
            draw_text('Changes start a new match when you resume.', tiny_font, (200, 200, 200),
                      SCREEN_WIDTH // 2, 322, center=True, shadow=False)

        draw_text('PLAYER 1', small_font, (110, 190, 255), 70, 352)
        draw_text('PLAYER 2', small_font, (255, 150, 90), 540, 352)
        for i, (a, b) in enumerate(zip(P1_KEYS, P2_KEYS)):
            draw_text(a, tiny_font, WHITE, 70, 386 + i * 24, shadow=False)
            draw_text(b, tiny_font, WHITE, 540, 386 + i * 24, shadow=False)
        draw_text('Tip: a whiffed heavy attack drains your special bar. Blocking breaks your shield for a few seconds.',
                  tiny_font, (200, 200, 200), SCREEN_WIDTH // 2, 540, center=True, shadow=False)
        if clicked(save_button):
            set_menu('main')


# ------------------------------------------------------------------ main loop
while run:
    clock.tick(FPS)
    frame_count += 1

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False
        elif event.type == pygame.KEYDOWN:
            key = event.key
            if game_paused:
                if menu_state == 'options':
                    if key == pygame.K_ESCAPE:
                        set_menu('main')
                elif key in (pygame.K_SPACE, pygame.K_RETURN) or (key in (pygame.K_ESCAPE, pygame.K_p) and match_in_progress):
                    resume_or_start()
            elif match_over:
                if key == pygame.K_RETURN:
                    new_match()
                elif key == pygame.K_ESCAPE:
                    go_to_menu()
            elif key in (pygame.K_ESCAPE, pygame.K_p, pygame.K_SPACE):
                game_paused = True
                set_menu('main')

    if game_paused:
        draw_menu()
        shake = (0, 0)
    else:
        update_game()
        draw_game()
        fx.draw_flash(canvas)
        shake = fx.shake_offset()

    screen.fill((0, 0, 0))
    screen.blit(canvas, shake)
    pygame.display.flip()

pygame.quit()