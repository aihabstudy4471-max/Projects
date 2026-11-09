
import math
import random
import pygame

FPS = 60
GRAVITY = 2
ANIM_STEP_FRAMES = 3      # 3 frames at 60 FPS = 50 ms per animation frame (same speed as before)
MAX_HEALTH = 250

# ---------------------------------------------------------------- balance table
ATTACKS = {
    # damage       : health removed on a clean hit
    # charge       : special-bar gained by the attacker on a hit
    # active       : animation frames in which the attack can connect
    # cooldown     : frames before the attacker can use it again
    # chip / lock  : health lost by the blocker, and frames the shield is down afterwards
    # knock        : knockback speed, shake / stop : screen shake + hit-stop frames
    'attack1': dict(damage=20, charge=35, active=(5, 6, 7), cooldown=35, chip=6, lock=150,
                    block_event='block1', knock=9, shake=3, stop=3, color=(255, 230, 120)),
    'attack2': dict(damage=35, charge=55, active=(5, 6, 7), cooldown=220, chip=6, lock=330,
                    block_event='block2', knock=18, shake=7, stop=6, color=(255, 150, 80)),
    'special': dict(damage=55, charge=0, active=(), cooldown=0, chip=18, lock=480,
                    block_event='block3', knock=26, shake=11, stop=9, color=(150, 220, 255)),
}
SPECIAL_SPEED = 12        # projectile speed (pixels per frame)
COMBO_WINDOW = 90         # frames you have to land the next hit to keep a combo going
COMBO_BONUS = 0.10        # +10% damage per hit already in the combo...
COMBO_MAX_STEPS = 3       # ...up to +30%
MISS_PENALTY = 25         # charge lost when a heavy attack whiffs

CONTROLS = {
    1: dict(left=pygame.K_a, right=pygame.K_d, jump=pygame.K_w,
            attack1=pygame.K_r, attack2=pygame.K_t, special=pygame.K_f, block=pygame.K_v),
    2: dict(left=pygame.K_j, right=pygame.K_l, jump=pygame.K_i,
            attack1=pygame.K_u, attack2=pygame.K_y, special=pygame.K_h, block=pygame.K_b),
}
NO_INPUT = {k: False for k in ('left', 'right', 'jump', 'attack1', 'attack2', 'special', 'block')}


# ---------------------------------------------------------------- small helpers
def make_glow(color, radius):
    """A soft round glow (used for projectiles, power-ups and speed aura)."""
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(radius, 0, -3):
        alpha = int(110 * (1 - i / radius) ** 2)
        pygame.draw.circle(surf, (*color, alpha), (radius, radius), i)
    return surf


class FX():
    """Particles, floating damage numbers, screen shake, hit-stop and screen flash."""

    def __init__(self, font=None, big_font=None):
        self.font = font
        self.big_font = big_font or font
        self.particles = []
        self.texts = []
        self.shake_power = 0.0
        self.hitstop = 0
        self.flash = 0

    def clear(self):
        self.particles.clear()
        self.texts.clear()
        self.shake_power = 0.0
        self.hitstop = 0
        self.flash = 0

    def burst(self, x, y, color, count=12, speed=6, life=(12, 26), size=(2, 5),
              gravity=0.3, angle=None, spread=math.tau):
        for _ in range(count):
            a = random.uniform(0, math.tau) if angle is None else angle + random.uniform(-spread / 2, spread / 2)
            s = random.uniform(speed * 0.35, speed)
            life_frames = random.randint(*life)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s,
                                   life_frames, life_frames, random.uniform(*size), color, gravity])

    def text(self, x, y, txt, color=(255, 255, 255), big=False):
        font = self.big_font if big else self.font
        if font is None:
            return
        img = font.render(txt, True, color)
        shadow = font.render(txt, True, (0, 0, 0))
        surf = pygame.Surface((img.get_width() + 3, img.get_height() + 3), pygame.SRCALPHA)
        surf.blit(shadow, (2, 2))
        surf.blit(img, (0, 0))
        self.texts.append([x - surf.get_width() / 2, y, surf, 50, 50])

    def shake(self, power):
        self.shake_power = max(self.shake_power, power)

    def stop(self, frames):
        self.hitstop = max(self.hitstop, frames)

    def shake_offset(self):
        if self.shake_power < 0.5:
            return (0, 0)
        p = int(self.shake_power)
        return (random.randint(-p, p), random.randint(-p, p))

    def update(self, frozen=False):
        self.shake_power *= 0.86
        self.flash = max(0, self.flash - 10)
        if frozen:
            return
        for p in self.particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += p[8]
            p[2] *= 0.97
            p[4] -= 1
        self.particles = [p for p in self.particles if p[4] > 0]
        for t in self.texts:
            t[1] -= 1.1
            t[3] -= 1
        self.texts = [t for t in self.texts if t[3] > 0]

    def draw(self, surface):
        for p in self.particles:
            r = max(1, int(p[6] * p[4] / p[5] + 0.5))
            pygame.draw.circle(surface, p[7], (int(p[0]), int(p[1])), r)
        for t in self.texts:
            t[2].set_alpha(int(255 * min(1.0, t[3] / (t[4] * 0.45))))
            surface.blit(t[2], (t[0], t[1]))

    def draw_flash(self, surface):
        if self.flash > 0:
            overlay = pygame.Surface(surface.get_size())
            overlay.fill((255, 255, 255))
            overlay.set_alpha(self.flash)
            surface.blit(overlay, (0, 0))


# ---------------------------------------------------------------- fighter
_anim_cache = {}


class Fighter():
    def __init__(self, player, x, y, flip, data, sprite_sheet, animation_steps, projectile_frames,
                 fx=None, name=None, controller=None, color=None):
        self.size = data[0]
        self.image_scale = data[1]
        self.offset = data[2]
        self.player = player
        self.name = name or ('P%d' % player)
        self.fx = fx
        self.controller = controller      # None = keyboard, otherwise a CPUController
        self.color = color or ((110, 190, 255) if player == 1 else (255, 150, 90))

        self.animation_list = self.load_images(sprite_sheet, animation_steps)
        self.action = 0   # 0 idle, 1 run, 2 jump, 3 attack1, 4 attack2, 5 special, 6 block, 7 hit, 8 death
        self.frame_index = 0
        self.anim_timer = 0
        self.image = self.animation_list[0][0]
        self.flip = flip
        self.rect = pygame.Rect((x, y, 80, 180))

        # movement
        self.vel_y = 0
        self.kb_x = 0.0
        self.running = False
        self.on_ground = True
        self.ground_y = self.rect.bottom
        self.jumps_remaining = 2
        self.jump_held = False
        self.speed = 10
        self.speed_boost = 0
        self.speed_boost_timer = 0
        self.speed_boost_max = 180
        self.step_timer = 0

        # health
        self.health = MAX_HEALTH
        self.lag_health = float(MAX_HEALTH)   # the white "damage trail" on the health bar
        self.lag_delay = 0
        self.alive = True
        self.hit = False
        self.hit_flash = 0

        # attacks
        self.attack1_active = False
        self.attack2_active = False
        self.attack3_active = False
        self.attack1_cooldown = 0
        self.attack2_cooldown = 0
        self.attack_landed = False
        self.special_fired = False
        self.attack_charge = 0
        self.max_charge = 250
        self.combo_count = 0
        self.combo_timer = 0

        # blocking
        self.blocking = False
        self.can_block = True
        self.block_cooldown = 0
        self.block_lock_total = 1

        # projectile
        self.projectile_frames = projectile_frames
        self.projectile_rect = None
        self.projectile_direction = 1
        self.projectile_frame_index = 0
        self.projectile_tick = 0

        # sound events - the main file reads these and plays the matching sound
        self.events = []

        # pre-rendered visuals
        self.glow = make_glow(self.color, 70)
        self.shadow_img = pygame.Surface((130, 26), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow_img, (0, 0, 0, 95), self.shadow_img.get_rect())
        self.shield_img = pygame.Surface((150, 220), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shield_img, (120, 200, 255, 55), self.shield_img.get_rect())
        pygame.draw.ellipse(self.shield_img, (190, 235, 255, 200), self.shield_img.get_rect(), 3)

    # ------------------------------------------------------------ setup
    def load_images(self, sprite_sheets, animation_steps):
        key = (tuple(id(s) for s in sprite_sheets), tuple(animation_steps), self.size, self.image_scale)
        if key in _anim_cache:       # slicing sheets is slow - only do it once per character
            return _anim_cache[key]
        animation_list = []
        for sheet, frame_count in zip(sprite_sheets, animation_steps):
            temp_img_list = []
            for x in range(frame_count):
                rect = pygame.Rect(x * self.size, 0, self.size, self.size)  # always row 0
                temp_img = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
                temp_img.blit(sheet, (0, 0), rect)
                temp_img_list.append(pygame.transform.scale(
                    temp_img, (int(self.size * self.image_scale), int(self.size * self.image_scale))))
            animation_list.append(temp_img_list)
        _anim_cache[key] = animation_list
        return animation_list

    def drain_events(self):
        events, self.events = self.events, []
        return events

    def read_input(self):
        if self.controller is not None:
            return self.controller.get_input()
        keys = pygame.key.get_pressed()
        return {name: bool(keys[code]) for name, code in CONTROLS[self.player].items()}

    def combo_multiplier(self):
        return 1 + COMBO_BONUS * min(self.combo_count, COMBO_MAX_STEPS)

    # ------------------------------------------------------------ movement + input
    def move(self, screen_width, screen_height, surface, target, locked):
        """Read input, apply physics. `locked` = countdown / round over (no control)."""
        dx = 0
        dy = 0
        self.running = False
        busy = self.attack1_active or self.attack2_active or self.attack3_active
        can_act = self.alive and not locked and not self.hit and not busy
        inp = self.read_input() if (self.alive and not locked) else NO_INPUT

        if can_act:
            self.blocking = bool(inp['block'] and self.can_block)
            move_speed = (self.speed + self.speed_boost) * (0.4 if self.blocking else 1)
            if inp['left']:
                dx -= move_speed
            if inp['right']:
                dx += move_speed
            self.running = dx != 0

            # jump (double jump) - only triggers on a fresh key press
            if inp['jump'] and not self.jump_held and self.jumps_remaining > 0:
                self.vel_y = -30
                self.jumps_remaining -= 1
                self.on_ground = False
                self.events.append('jump')
                self.dust(3)

            # attacks
            if inp['attack1'] and self.attack1_cooldown <= 0:
                self.start_attack('attack1')
            elif inp['attack2'] and self.attack2_cooldown <= 0:
                self.start_attack('attack2')
            elif inp['special'] and self.attack_charge >= self.max_charge:
                self.start_attack('special')
        else:
            self.blocking = False
        self.jump_held = bool(inp['jump'])

        # knockback slides you back and fades out
        dx += self.kb_x
        self.kb_x *= 0.8
        if abs(self.kb_x) < 0.5:
            self.kb_x = 0

        # gravity + floor
        self.vel_y += GRAVITY
        dy += self.vel_y
        self.ground_y = screen_height - 20
        impact = self.vel_y
        self.on_ground = False
        if self.rect.bottom + dy >= self.ground_y:
            if impact > 14:
                self.dust(6)
            self.vel_y = 0
            self.jumps_remaining = 2
            dy = self.ground_y - self.rect.bottom
            self.on_ground = True

        # screen edges
        if self.rect.left + dx < 0:
            dx = -self.rect.left
        if self.rect.right + dx > screen_width:
            dx = screen_width - self.rect.right

        # always face the opponent
        self.flip = target.rect.centerx <= self.rect.centerx

        self.rect.x += dx
        self.rect.y += dy

        # fighters can't walk through each other (you can still jump over)
        if (self.alive and target.alive and self.rect.colliderect(target.rect)
                and self.rect.bottom > target.rect.top + 50 and self.rect.top < target.rect.bottom - 50):
            if self.rect.centerx < target.rect.centerx:
                self.rect.right = target.rect.left
            else:
                self.rect.left = target.rect.right
            self.rect.left = max(0, self.rect.left)
            self.rect.right = min(screen_width, self.rect.right)

        # timers
        if not self.attack1_active and self.attack1_cooldown > 0:
            self.attack1_cooldown -= 1
        if not self.attack2_active and self.attack2_cooldown > 0:
            self.attack2_cooldown -= 1
        if not self.can_block:
            self.block_cooldown -= 1
            if self.block_cooldown <= 0:
                self.can_block = True
        if self.speed_boost_timer > 0:
            self.speed_boost_timer -= 1
            if self.speed_boost_timer <= 0:
                self.speed_boost = 0
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer <= 0:
                self.combo_count = 0
        if self.hit_flash > 0:
            self.hit_flash -= 1

        # footsteps + dust
        if self.running and self.on_ground:
            self.step_timer -= 1
            if self.step_timer <= 0:
                self.step_timer = 14 if self.speed_boost == 0 else 8
                self.events.append('step')
                self.dust(2)
        else:
            self.step_timer = 0

    def dust(self, count):
        if self.fx:
            self.fx.burst(self.rect.centerx, self.rect.bottom - 4, (205, 195, 175), count,
                          speed=3, life=(10, 20), size=(2, 4), gravity=-0.02)

    def start_attack(self, kind):
        self.blocking = False
        self.attack_landed = False
        self.special_fired = False
        if kind == 'attack1':
            self.attack1_active = True
            self.events.append('attack1')
        elif kind == 'attack2':
            self.attack2_active = True
            self.events.append('attack2')
        else:
            self.attack3_active = True
            self.events.append('attack3')

    def cancel_attacks(self):
        if self.attack1_active:
            self.attack1_cooldown = max(self.attack1_cooldown, 20)
        if self.attack2_active:
            self.attack2_cooldown = max(self.attack2_cooldown, 60)
        self.attack1_active = self.attack2_active = self.attack3_active = False

    # ------------------------------------------------------------ per-frame update
    def update(self, surface, target, screen_width):
        # white damage-trail on the health bar
        if self.lag_health > self.health:
            if self.lag_delay > 0:
                self.lag_delay -= 1
            else:
                self.lag_health = max(self.health, self.lag_health - 1.1)
        else:
            self.lag_health = self.health

        # pick the animation
        if not self.alive:
            new_action = 8
        elif self.hit:
            new_action = 7
        elif self.attack1_active:
            new_action = 3
        elif self.attack2_active:
            new_action = 4
        elif self.attack3_active:
            new_action = 5
        elif not self.on_ground:
            new_action = 2
        elif self.blocking:
            new_action = 6
        elif self.running:
            new_action = 1
        else:
            new_action = 0
        self.update_action(new_action)

        frames = self.animation_list[self.action]
        self.frame_index = min(self.frame_index, len(frames) - 1)
        self.image = frames[self.frame_index]

        self.resolve_attacks(target)
        self.update_projectile(target, screen_width)
        self.advance_animation(frames)

    def update_action(self, new_action):
        if new_action != self.action:
            self.action = new_action
            self.frame_index = 0
            self.anim_timer = 0

    def advance_animation(self, frames):
        self.anim_timer += 1
        if self.anim_timer < ANIM_STEP_FRAMES:
            return
        self.anim_timer = 0
        if self.frame_index < len(frames) - 1:
            self.frame_index += 1
        elif not self.alive:
            pass                                  # stay on the last death frame
        else:
            self.finish_action()

    def finish_action(self):
        """Called when a one-shot animation reaches its last frame."""
        if self.action == 3:
            self.attack1_active = False
            self.attack1_cooldown = ATTACKS['attack1']['cooldown']
        elif self.action == 4:
            self.attack2_active = False
            self.attack2_cooldown = ATTACKS['attack2']['cooldown']
            if not self.attack_landed:            # whiffing a heavy attack costs charge
                self.attack_charge = max(0, self.attack_charge - MISS_PENALTY)
                if self.fx:
                    self.fx.text(self.rect.centerx, self.rect.top - 10, 'MISS', (190, 190, 190))
        elif self.action == 5:
            self.attack3_active = False
        elif self.action == 7:
            self.hit = False
        else:
            self.frame_index = 0                  # looping animation

    # ------------------------------------------------------------ combat
    def attack_rect(self):
        return pygame.Rect(self.rect.centerx - (2 * self.rect.width * self.flip),
                           self.rect.y, 2 * self.rect.width, self.rect.height)

    def resolve_attacks(self, target):
        kind = 'attack1' if self.attack1_active else 'attack2' if self.attack2_active else None
        if kind and not self.attack_landed and target.alive \
                and self.frame_index in ATTACKS[kind]['active']:
            if self.attack_rect().colliderect(target.rect):
                target.receive_attack(self, kind)
                self.attack_landed = True

        # the special fires a projectile partway through its animation
        if self.attack3_active and not self.special_fired and self.frame_index >= 3:
            self.special_fired = True
            if self.projectile_rect is None and self.attack_charge >= self.max_charge:
                self.projectile_direction = -1 if self.flip else 1
                self.projectile_rect = self.projectile_frames[0].get_rect(
                    center=(self.rect.centerx + self.projectile_direction * 40, self.rect.centery - 10))
                self.attack_charge = 0
                if self.fx:
                    self.fx.burst(self.projectile_rect.centerx, self.projectile_rect.centery,
                                  self.color, 14, 6, gravity=0)

    def receive_attack(self, attacker, kind):
        """Something hit me. Returns 'hit', 'blocked' or None."""
        if not self.alive:
            return None
        data = ATTACKS[kind]
        direction = 1 if self.rect.centerx >= attacker.rect.centerx else -1
        fx = self.fx
        px = self.rect.centerx - direction * 25
        py = self.rect.centery - 30

        if self.blocking and self.can_block:
            self.health -= data['chip']
            self.can_block = False
            self.blocking = False
            self.block_cooldown = data['lock']
            self.block_lock_total = data['lock']
            self.kb_x = direction * data['knock'] * 0.4
            self.attack_charge = min(self.attack_charge + 10, self.max_charge)   # reward for blocking
            self.events.append(data['block_event'])
            if fx:
                fx.burst(px, py, (170, 225, 255), 16, 8, gravity=0.2)
                fx.text(self.rect.centerx, self.rect.top - 10, 'BLOCKED', (170, 225, 255))
                fx.shake(3)
                fx.stop(3)
            if self.health <= 0:
                self.die()
            return 'blocked'

        damage = int(round(data['damage'] * attacker.combo_multiplier()))
        self.health -= damage
        self.lag_delay = 25
        self.hit = True
        self.hit_flash = 6
        self.combo_count = 0
        self.combo_timer = 0
        if self.action == 7:                      # hit again while stunned: restart the flinch
            self.frame_index = 0
            self.anim_timer = 0
        self.cancel_attacks()
        self.kb_x = direction * data['knock']
        self.events.append('hit')

        attacker.attack_charge = min(attacker.attack_charge + data['charge'], attacker.max_charge)
        attacker.combo_count += 1
        attacker.combo_timer = COMBO_WINDOW

        if fx:
            fx.burst(px, py, data['color'], 10 + damage // 4, 9, life=(14, 30), gravity=0.35)
            fx.burst(px, py, (255, 255, 255), 5, 5, life=(6, 12))
            fx.text(self.rect.centerx, self.rect.top - 10, '-%d' % damage, data['color'], big=damage >= 30)
            fx.shake(data['shake'])
            fx.stop(data['stop'])
        if self.health <= 0:
            self.die()
        return 'hit'

    def die(self):
        self.health = 0
        self.alive = False
        self.blocking = False
        self.hit = False
        self.cancel_attacks()
        self.events.append('death')
        if self.fx:
            self.fx.stop(18)
            self.fx.shake(16)
            self.fx.flash = 190
            self.fx.burst(self.rect.centerx, self.rect.centery, (255, 255, 255), 30, 12, life=(20, 40), gravity=0.3)
            self.fx.burst(self.rect.centerx, self.rect.centery, self.color, 30, 9, life=(20, 40), gravity=0.3)

    # ------------------------------------------------------------ projectile
    def update_projectile(self, target, screen_width):
        p = self.projectile_rect
        if p is None:
            return
        p.x += SPECIAL_SPEED * self.projectile_direction
        self.projectile_tick += 1
        if self.projectile_tick % 2 == 0:
            self.projectile_frame_index = (self.projectile_frame_index + 1) % len(self.projectile_frames)
        if self.fx and self.projectile_tick % 2 == 0:
            self.fx.burst(p.centerx - self.projectile_direction * 30, p.centery, self.color, 2, 2,
                          life=(8, 16), size=(2, 4), gravity=0)

        hitbox = p.inflate(-60, -60)
        if target.alive and hitbox.colliderect(target.rect):
            result = target.receive_attack(self, 'special')
            if self.fx:
                self.fx.burst(hitbox.centerx, hitbox.centery, (255, 255, 255), 10, 8, gravity=0.1)
            self.projectile_rect = None
            return
        if target.projectile_rect is not None and hitbox.colliderect(target.projectile_rect.inflate(-60, -60)):
            if self.fx:
                self.fx.burst(hitbox.centerx, hitbox.centery, (255, 255, 255), 24, 10, gravity=0.1)
                self.fx.shake(5)
            self.projectile_rect = None
            target.projectile_rect = None
            return
        if p.right < -60 or p.left > screen_width + 60:
            self.projectile_rect = None

    # ------------------------------------------------------------ drawing
    def draw(self, surface):
        # shadow on the floor (shrinks when you jump)
        height = max(0, self.ground_y - self.rect.bottom)
        shrink = max(0.35, 1 - height / 500)
        shadow = pygame.transform.smoothscale(self.shadow_img, (int(130 * shrink), int(26 * shrink)))
        surface.blit(shadow, shadow.get_rect(center=(self.rect.centerx, self.ground_y - 2)))

        if self.speed_boost > 0 and self.alive:
            if self.speed_boost_timer > 60 or (self.speed_boost_timer // 6) % 2 == 0:
                surface.blit(self.glow, self.glow.get_rect(center=self.rect.center))

        img = pygame.transform.flip(self.image, self.flip, False)
        if self.hit_flash > 0:
            img = img.copy()
            img.fill((110, 110, 110, 0), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(img, (self.rect.x - (self.offset[0] * self.image_scale),
                           self.rect.y - (self.offset[1] * self.image_scale)))

        if self.blocking and self.alive:
            surface.blit(self.shield_img, self.shield_img.get_rect(center=self.rect.center))

    def draw_projectile(self, surface):
        if self.projectile_rect is None:
            return
        surface.blit(self.glow, self.glow.get_rect(center=self.projectile_rect.center))
        img = pygame.transform.flip(self.projectile_frames[self.projectile_frame_index],
                                    self.projectile_direction < 0, False)
        surface.blit(img, self.projectile_rect)


# ---------------------------------------------------------------- CPU opponent
class CPUController():
    """Presses 'virtual keys' for a fighter. Pass it to Fighter(controller=...) then call bind()."""
    LEVELS = {
        'easy':   dict(think=22, block=0.25, dodge=0.15, aggression=0.35, special=0.4),
        'normal': dict(think=14, block=0.55, dodge=0.35, aggression=0.55, special=0.7),
        'hard':   dict(think=7,  block=0.85, dodge=0.60, aggression=0.80, special=1.0),
    }

    def __init__(self, difficulty='normal'):
        self.cfg = self.LEVELS.get(difficulty, self.LEVELS['normal'])
        self.fighter = None
        self.target = None
        self.timer = 30
        self.cmd = dict(NO_INPUT)
        self.pulses = set()
        self.threat_active = False
        self.react_block = False

    def bind(self, fighter, target):
        self.fighter = fighter
        self.target = target

    def get_input(self):
        f, t = self.fighter, self.target
        out = dict(NO_INPUT)
        if f is None or t is None or not f.alive or not t.alive:
            return out
        self.timer -= 1
        if self.timer <= 0:
            self.think()
            self.timer = self.cfg['think'] + random.randint(0, 4)

        # reactions are checked every frame so the CPU can block / dodge in time
        threat = self.detect_threat()
        if threat and not self.threat_active:
            self.react_block = random.random() < self.cfg['block']
            if not self.react_block and random.random() < self.cfg['dodge']:
                self.pulses.add('jump')
        self.threat_active = threat

        out.update(self.cmd)
        for key in self.pulses:
            out[key] = True
        self.pulses.clear()
        if threat and self.react_block and f.can_block:
            out['block'] = True
        return out

    def detect_threat(self):
        f, t = self.fighter, self.target
        if (t.attack1_active or t.attack2_active) and abs(t.rect.centerx - f.rect.centerx) < 230 \
                and t.frame_index <= 6:
            return True
        p = t.projectile_rect
        if p is not None and abs(p.centerx - f.rect.centerx) < 320 \
                and (f.rect.centerx - p.centerx) * t.projectile_direction > 0:
            return True
        return False

    def think(self):
        f, t, cfg = self.fighter, self.target, self.cfg
        dist = t.rect.centerx - f.rect.centerx
        adist = abs(dist)
        toward = 'right' if dist > 0 else 'left'
        away = 'left' if dist > 0 else 'right'
        same_level = abs(t.rect.bottom - f.rect.bottom) < 140
        self.cmd['left'] = self.cmd['right'] = False

        if f.attack_charge >= f.max_charge and same_level and adist > 150 \
                and random.random() < cfg['special'] * 0.6:
            self.pulses.add('special')
        elif adist > 200:
            self.cmd[toward] = True                    # close the gap
            if random.random() < 0.06:
                self.pulses.add('jump')
        else:
            r = random.random()
            if r < cfg['aggression'] and same_level:
                if f.attack2_cooldown <= 0 and random.random() < 0.35:
                    self.pulses.add('attack2')
                elif f.attack1_cooldown <= 0:
                    self.pulses.add('attack1')
            elif r < cfg['aggression'] + 0.2 or f.health < 70:
                self.cmd[away] = True                  # back off for a moment
            if random.random() < 0.05:
                self.pulses.add('jump')


# ---------------------------------------------------------------- buttons
class button():
    def __init__(self, x, y, image, scale):
        width = image.get_width()
        height = image.get_height()
        self.image = pygame.transform.scale(image, (int(width * scale), int(height * scale)))
        self.rect = self.image.get_rect()
        self.rect.topleft = (x, y)
        self.clicked = False

    def draw(self, screen):
        action = False
        mouse_pos = pygame.mouse.get_pos()
        hovering = self.rect.collidepoint(mouse_pos)
        if hovering:
            if pygame.mouse.get_pressed()[0] == 1 and self.clicked == False:
                self.clicked = True
                action = True
        if pygame.mouse.get_pressed()[0] == 0:
            self.clicked = False

        img = self.image
        if hovering:                                  # brighten when hovered
            img = self.image.copy()
            img.fill((35, 35, 35, 0), special_flags=pygame.BLEND_RGB_ADD)
        screen.blit(img, (self.rect.x, self.rect.y))
        return action


class text_button():
    """A simple rounded text button (used on the options screen)."""

    def __init__(self, x, y, w, h, font):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = font
        self.clicked = False

    def draw(self, surface, label):
        action = False
        hovering = self.rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (60, 85, 130) if hovering else (35, 45, 75), self.rect, border_radius=10)
        pygame.draw.rect(surface, (180, 205, 255), self.rect, 2, border_radius=10)
        img = self.font.render(label, True, (255, 255, 255))
        surface.blit(img, img.get_rect(center=self.rect.center))
        if hovering and pygame.mouse.get_pressed()[0] and not self.clicked:
            self.clicked = True
            action = True
        if not pygame.mouse.get_pressed()[0]:
            self.clicked = False
        return action


# ---------------------------------------------------------------- power-ups
class power_up():
    def __init__(self, kind, radius=None, screen_width=1000):
        self.kind = kind
        self.screen_width = screen_width
        self.active = True
        self.age = 0
        self.direction_x = random.choice([-1, 1])
        self.direction_y = random.choice([-1, 1])
        self.x = -30 if self.direction_x == 1 else screen_width + 30
        self.y = 200

        if kind == 'health':
            self.color = (255, 165, 0)
            self.radius = radius or 14
            self.speed = 3
        elif kind == 'speed':
            self.color = (0, 255, 0)
            self.radius = radius or 15
            self.speed = 5
            self.y = 400
        else:  # charge
            self.color = (0, 120, 255)
            self.radius = radius or 15
            self.speed = 5
            self.y = random.randint(100, 400)
        self.glow = make_glow(self.color, self.radius * 3)
        self.rect = pygame.Rect(0, 0, self.radius * 2, self.radius * 2)

    def update(self, screen=None, t=None):
        if not self.active:
            return None
        self.age += 1
        self.x += self.speed * self.direction_x
        if self.kind == 'health':
            self.y = 200 + 90 * math.sin(self.age * 0.06)
        elif self.kind == 'charge':
            self.y += self.speed * 0.6 * self.direction_y
            if self.y < 80 or self.y > 560:
                self.direction_y *= -1
        self.rect.center = (int(self.x), int(self.y))
        return self.rect

    def off_screen(self):
        return self.x < -60 or self.x > self.screen_width + 60

    def draw(self, surface):
        if not self.active:
            return
        cx, cy = int(self.x), int(self.y)
        pulse = 1 + 0.12 * math.sin(self.age * 0.2)
        surface.blit(self.glow, self.glow.get_rect(center=(cx, cy)))
        r = int(self.radius * pulse)
        pygame.draw.circle(surface, self.color, (cx, cy), r)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), r, 2)
        w = (255, 255, 255)
        if self.kind == 'health':        # plus sign
            pygame.draw.rect(surface, w, (cx - 2, cy - 7, 4, 14))
            pygame.draw.rect(surface, w, (cx - 7, cy - 2, 14, 4))
        elif self.kind == 'speed':       # double arrow
            for off in (-5, 3):
                pygame.draw.polygon(surface, w, [(cx + off, cy - 7), (cx + off + 6, cy), (cx + off, cy + 7)])
        else:                            # lightning bolt
            pygame.draw.polygon(surface, w, [(cx + 3, cy - 9), (cx - 5, cy + 1), (cx, cy + 1),
                                             (cx - 3, cy + 9), (cx + 6, cy - 2), (cx + 1, cy - 2)])

    def apply_effect(self, fighter, fx=None):
        if self.kind == 'health':
            fighter.health = min(fighter.health + 30, MAX_HEALTH)
            label = '+30 HP'
        elif self.kind == 'speed':
            fighter.speed_boost = 10
            fighter.speed_boost_timer = 180
            fighter.speed_boost_max = 180
            label = 'SPEED!'
        else:
            fighter.attack_charge = min(fighter.attack_charge + 40, fighter.max_charge)
            label = '+CHARGE'
        if fx:
            fx.text(fighter.rect.centerx, fighter.rect.top - 20, label, self.color)
            fx.burst(self.x, self.y, self.color, 18, 7, gravity=0.1)
        self.active = False


