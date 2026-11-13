import array
import json
import math
import os
import random
import sys
import traceback

import pygame

# --- Config ---
WIDTH, HEIGHT = 1024, 720
FPS = 60

# Colors
BLACK = (10, 10, 12)
DARK = (25, 25, 30)
GRAY = (80, 80, 90)
LIGHT_GRAY = (140, 140, 150)
WHITE = (240, 240, 240)
RED = (200, 50, 50)
GREEN = (60, 200, 90)
BLUE = (70, 120, 220)
YELLOW = (230, 210, 80)
AMBER = (255, 180, 60)
PURPLE = (150, 80, 200)
DOOR_GRAY = (55, 55, 65)

ROOMS = [
    "Jenifer's Bedroom",
    "Upstairs Hall",
    "Living Room",
    "Dining Room",
    "Bathroom",
    "Kitchen",
    "Left Hallway",
    "Right Hallway",
    "Bedroom L Door",
    "Bedroom R Door",
]

# Adjacency/path graph for Ms. Jenifer AI movement (inside her house)
PATHS = {
    "Jenifer's Bedroom": ["Upstairs Hall", "Living Room", "Dining Room"],
    "Upstairs Hall": ["Jenifer's Bedroom", "Left Hallway", "Bathroom"],
    "Living Room": ["Jenifer's Bedroom", "Right Hallway", "Kitchen"],
    "Dining Room": ["Jenifer's Bedroom", "Upstairs Hall", "Bathroom"],
    "Bathroom": ["Dining Room", "Upstairs Hall", "Left Hallway"],
    "Kitchen": ["Living Room", "Right Hallway"],
    "Left Hallway": ["Upstairs Hall", "Bathroom", "Bedroom L Door"],
    "Right Hallway": ["Living Room", "Kitchen", "Bedroom R Door"],
    "Bedroom L Door": ["Left Hallway"],
    "Bedroom R Door": ["Right Hallway"],
}

CAM_POS = {
    "Jenifer's Bedroom": (120, 120),
    "Upstairs Hall": (260, 180),
    "Living Room": (520, 180),
    "Dining Room": (120, 260),
    "Bathroom": (120, 380),
    "Kitchen": (520, 300),
    "Left Hallway": (260, 380),
    "Right Hallway": (520, 380),
    "Bedroom L Door": (260, 480),
    "Bedroom R Door": (520, 480),
}

NIGHT_LENGTH_SECONDS = 360  # 6 real minutes per night = 6 in-game hours
HOUR_SECONDS = NIGHT_LENGTH_SECONDS / 6


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class MsJeniferAI:
    def __init__(self, night):
        self.night = night
        self.location = "Jenifer's Bedroom"
        self.is_monster = (night >= 8)
        # AI level roughly increases per night (FNAF-like movement opportunity levels)
        # Night 5 is the final story night (hard), 6-8 are bonus nights
        self.base_level = {1: 2, 2: 4, 3: 6, 4: 9, 5: 15, 6: 12, 7: 15, 8: 20}.get(night, 10)
        self.level = self.base_level
        self.anger = 35.0 if self.is_monster else 0.0  # 0-100, monster starts angry
        self.move_timer = 0.0
        self.move_interval = 5.0  # movement opportunity baseline
        self.at_door_side = None  # "left" or "right" when in bedroom doorway
        self.door_patience = 0.0
        self.attack_pending = False

    def reset_for_night(self, night):
        self.__init__(night)

    def add_anger(self, amount):
        self.anger = clamp(self.anger + amount, 0.0, 100.0)

    def update(self, dt, left_door_closed, right_door_closed, player_hiding=False, watched=False):
        self.move_timer += dt
        self.door_patience += dt
        # anger behavior
        if self.is_monster:
            self.anger = clamp(self.anger - dt * 0.35 + dt * 0.6, 0.0, 100.0)  # volatile, trends up
            if watched:
                self.add_anger(dt * 5.0)
            self.level = 20
            move_interval = random.uniform(1.2, 3.0)
            # occasional random rage spikes
            if random.random() < dt * 0.25:
                self.add_anger(random.uniform(2.0, 8.0))
        else:
            self.anger = clamp(self.anger - dt * 1.2, 0.0, 100.0)
            if watched:
                self.add_anger(dt * 2.0)
            self.level = clamp(self.base_level + int(self.anger // 20), 0, 20)
            move_interval = max(2.8, 5.0 - self.anger * 0.03)

        # If she's at a bedroom door, she waits for an opening (max 10s in doorway)
        if self.location == "Bedroom L Door":
            self.at_door_side = "left"
            if self.door_patience > 10.0:
                self.location = random.choice(["Left Hallway", "Bathroom", "Upstairs Hall"])
                self.door_patience = 0.0
                return
            if self.is_monster:
                patience_need = random.uniform(1.2, 3.2) - self.anger * 0.01
                leave_need = random.uniform(1.5, 3.5) + (1.2 if player_hiding else 0.0)
            else:
                patience_need = random.uniform(3.0, 6.0) - self.anger * 0.015
                leave_need = random.uniform(2.5, 5.5) + (2.0 if player_hiding else 0.0)
            if not left_door_closed and self.door_patience > max(0.8 if self.is_monster else 1.8, patience_need):
                self.attack_pending = True
            elif (left_door_closed or player_hiding) and self.door_patience > max(1.0 if self.is_monster else 1.8, leave_need):
                # forced back / loses interest if you hide quietly (monster may fake out nearby)
                if self.is_monster and random.random() < 0.35 and not player_hiding:
                    self.location = random.choice(["Left Hallway", "Bedroom L Door", "Upstairs Hall"])
                else:
                    self.location = random.choice(["Left Hallway", "Bathroom", "Upstairs Hall"])
                self.door_patience = 0.0
                if left_door_closed:
                    self.add_anger(12.0 if self.is_monster else 8.0)
            elif self.is_monster and left_door_closed and random.random() < dt * 0.35:
                # monster can randomly switch sides or reposition
                self.location = random.choice(["Left Hallway", "Upstairs Hall", "Right Hallway", "Bedroom R Door"])
                self.door_patience = 0.0
            return
        elif self.location == "Bedroom R Door":
            self.at_door_side = "right"
            if self.door_patience > 10.0:
                self.location = random.choice(["Right Hallway", "Kitchen", "Living Room"])
                self.door_patience = 0.0
                return
            if self.is_monster:
                patience_need = random.uniform(1.2, 3.2) - self.anger * 0.01
                leave_need = random.uniform(1.5, 3.5) + (1.2 if player_hiding else 0.0)
            else:
                patience_need = random.uniform(3.0, 6.0) - self.anger * 0.015
                leave_need = random.uniform(2.5, 5.5) + (2.0 if player_hiding else 0.0)
            if not right_door_closed and self.door_patience > max(0.8 if self.is_monster else 1.8, patience_need):
                self.attack_pending = True
            elif (right_door_closed or player_hiding) and self.door_patience > max(1.0 if self.is_monster else 1.8, leave_need):
                if self.is_monster and random.random() < 0.35 and not player_hiding:
                    self.location = random.choice(["Right Hallway", "Bedroom R Door", "Living Room"])
                else:
                    self.location = random.choice(["Right Hallway", "Kitchen", "Living Room"])
                self.door_patience = 0.0
                if right_door_closed:
                    self.add_anger(12.0 if self.is_monster else 8.0)
            elif self.is_monster and right_door_closed and random.random() < dt * 0.35:
                self.location = random.choice(["Right Hallway", "Living Room", "Left Hallway", "Bedroom L Door"])
                self.door_patience = 0.0
            return
        else:
            self.at_door_side = None

        # monster random teleport/reposition for unpredictability
        if self.is_monster and random.random() < dt * 0.12:
            self.location = random.choice([
                "Upstairs Hall", "Left Hallway", "Right Hallway", "Living Room",
                "Dining Room", "Kitchen", "Bathroom", "Bedroom L Door", "Bedroom R Door"
            ])
            self.door_patience = 0.0
            self.move_timer = 0.0
            return

        if self.move_timer < move_interval:
            return
        self.move_timer = 0.0

        # Movement opportunity
        chance_level = 20 if self.is_monster else self.level
        if random.randint(1, 20) > chance_level:
            # monster gets extra attempts
            if not (self.is_monster and random.random() < 0.55):
                return

        options = PATHS.get(self.location, [])
        if not options:
            return

        # Bias toward doors as difficulty/anger increases (monster heavily biased and erratic)
        weights = []
        for opt in options:
            w = 1.0 + random.uniform(0, 0.5 if self.is_monster else 0.15)
            if "Door" in opt:
                w += 1.5 + self.level * 0.18 + self.anger * 0.02 + (2.0 if self.is_monster else 0.0)
            elif "Hall" in opt and "Door" not in opt:
                w += 0.7 + self.anger * 0.008 + (0.8 if self.is_monster else 0.0)
            elif opt == "Jenifer's Bedroom":
                w *= 0.35 if self.is_monster else 0.5
            weights.append(w)

        nxt = random.choices(options, weights=weights, k=1)[0]
        # monster may chain extra moves unpredictably
        if self.is_monster and "Door" not in nxt and random.random() < 0.4:
            opts2 = PATHS.get(nxt, [])
            if opts2:
                nxt = random.choice(opts2)
        self.location = nxt
        self.door_patience = 0.0


class DadAI:
    """Liam's dad - wanders the house at night. If he catches Liam, he lectures him and makes Jenifer mad."""
    def __init__(self, night):
        self.night = night
        self.location = "Kitchen"
        self.move_timer = 0.0
        self.move_interval = 7.0
        self.door_patience = 0.0
        self.active = night >= 2  # appears from night 2 onward

    def update(self, dt, left_light, right_light, left_door, right_door, hiding, anger_ref):
        if not self.active:
            return None
        self.move_timer += dt
        self.door_patience += dt
        event = None

        if self.location == "Bedroom L Door":
            # If Liam is exposed, dad catches him and gives a lecture (makes Jenifer mad)
            if not hiding and (left_light or not left_door):
                if self.door_patience > 2.5:
                    event = "lecture_left"
                    self.location = random.choice(["Left Hallway", "Upstairs Hall"])
                    self.door_patience = 0.0
                    self.move_timer = 0.0
            elif left_door or hiding:
                if self.door_patience > 3.0:
                    self.location = "Left Hallway"
                    self.door_patience = 0.0
            return event
        if self.location == "Bedroom R Door":
            if not hiding and (right_light or not right_door):
                if self.door_patience > 2.5:
                    event = "lecture_right"
                    self.location = random.choice(["Right Hallway", "Living Room"])
                    self.door_patience = 0.0
                    self.move_timer = 0.0
            elif right_door or hiding:
                if self.door_patience > 3.0:
                    self.location = "Right Hallway"
                    self.door_patience = 0.0
            return event

        if self.move_timer < self.move_interval:
            return None
        self.move_timer = 0.0
        # simple wandering toward halls/doors occasionally
        paths = {
            "Kitchen": ["Living Room", "Right Hallway"],
            "Living Room": ["Kitchen", "Right Hallway", "Upstairs Hall"],
            "Upstairs Hall": ["Living Room", "Left Hallway", "Bathroom"],
            "Bathroom": ["Upstairs Hall", "Left Hallway"],
            "Left Hallway": ["Upstairs Hall", "Bathroom", "Bedroom L Door"],
            "Right Hallway": ["Kitchen", "Living Room", "Bedroom R Door"],
            "Jenifer's Bedroom": ["Upstairs Hall"],
            "Dining Room": ["Living Room", "Kitchen"],
        }
        options = paths.get(self.location, ["Upstairs Hall"])
        # mild bias to doors at higher nights
        weights = []
        for o in options:
            w = 1.0
            if "Door" in o:
                w += 0.3 + self.night * 0.1
            weights.append(w)
        self.location = random.choices(options, weights=weights, k=1)[0]
        self.door_patience = 0.0
        return None


class Game:
    def __init__(self):
        try:
            pygame.mixer.pre_init(44100, -16, 1, 512)
        except Exception:
            pass
        pygame.init()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            pass
        pygame.display.set_caption("Five Nights at Jenifer's House")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 24)
        self.big_font = pygame.font.SysFont("consolas", 48)
        self.small_font = pygame.font.SysFont("consolas", 18)
        self.title_font = pygame.font.SysFont("consolas", 64, bold=True)
        self.sounds = self._build_sounds()

        self.state = "menu"  # menu, custom_night, night_intro, playing, jumpscare, win_night, win_game, gameover
        self.night = 1
        self.max_night = 8
        self.custom_ai_level = 10
        self.custom_night_mode = False
        self.confirm_quit = False
        self.confirm_action = "quit_app"  # quit_app | abandon_night
        self.paused = False
        self.save_path = os.path.join(os.path.dirname(__file__), "save.json")
        self.unlocked_night = self.load_progress()

        self.reset_night()

    def _tone(self, freq=440, ms=120, vol=0.25, wave="square"):
        try:
            sr = 44100
            n = max(1, int(sr * ms / 1000))
            amp = int(32767 * vol)
            buf = array.array("h")
            for i in range(n):
                t = i / sr
                if wave == "noise":
                    v = random.uniform(-1, 1)
                else:
                    s = math.sin(2 * math.pi * freq * t)
                    if wave == "square":
                        v = 1.0 if s >= 0 else -1.0
                    elif wave == "saw":
                        v = 2.0 * ((freq * t) % 1.0) - 1.0
                    else:
                        v = s
                env = min(1.0, i / max(1, n * 0.05), (n - i) / max(1, n * 0.2))
                buf.append(int(amp * v * env))
            return pygame.mixer.Sound(buffer=buf)
        except Exception:
            return None

    def _build_sounds(self):
        sounds = {}
        specs = {
            "blip": (880, 60, 0.18, "square"),
            "door": (180, 120, 0.22, "square"),
            "camera": (520, 80, 0.15, "sine"),
            "warn": (220, 180, 0.22, "saw"),
            "anger": (140, 220, 0.25, "saw"),
            "lecture": (260, 260, 0.2, "square"),
            "jumpscare": (90, 500, 0.35, "noise"),
            "win": (660, 220, 0.2, "sine"),
        }
        for k, spec in specs.items():
            sounds[k] = self._tone(*spec)
        return sounds

    def play_sound(self, name):
        try:
            snd = self.sounds.get(name)
            if snd:
                snd.play()
        except Exception:
            pass

    def load_progress(self):
        try:
            with open(self.save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return int(clamp(data.get("unlocked_night", 1), 1, 8))
        except Exception:
            return 1

    def save_progress(self):
        try:
            with open(self.save_path, "w", encoding="utf-8") as f:
                json.dump({"unlocked_night": self.unlocked_night}, f)
        except Exception:
            pass

    def reset_night(self):
        self.ai = MsJeniferAI(self.night)
        self.dad = DadAI(self.night)
        self.time_elapsed = 0.0
        self.hour = 12  # 12 AM
        self.power = 100.0
        self.usage = 1  # bars 1-4
        self.left_door = False
        self.right_door = False
        self.left_light = False
        self.right_light = False
        self.camera_up = False
        self.current_cam = "Jenifer's Bedroom"
        self.message = ""
        self.message_timer = 0.0
        self.jumpscare_timer = 0.0
        self.intro_timer = 0.0
        self.static_timer = 0.0
        self.blackout = False
        self.blackout_timer = 0.0
        self.ui = {}  # clickable rects populated during draw
        self.cam_buttons = {}
        self.left_door_anim = 0.0
        self.right_door_anim = 0.0
        self.cam_anim = 0.0
        self.toast = ""
        self.toast_timer = 0.0
        self.hiding = False
        self.hide_time_left = 30.0
        self.was_watched = False
        self.paused = False
        self.last_hour_mark = 12
        self.ambience_msg = ""
        self.ambience_timer = 0.0
        self.left_door_cooldown = 0.0
        self.right_door_cooldown = 0.0
        self.left_door_close_timer = 0.0
        self.right_door_close_timer = 0.0
        self.cutscene_timer = 0.0
        # stats
        self.stats_hides = 0
        self.stats_lectures = 0
        self.stats_door_blocks = 0
        self.stats_cam_toggles = 0
        self.stats_peak_anger = 0.0
        self.stats_survived_encounters = 0
        self.night_summary = {}

    def start_night(self, night, ai_level=None):
        self.night = night
        self.reset_night()
        if ai_level is not None:
            lvl = int(clamp(ai_level, 0, 20))
            self.ai.base_level = lvl
            self.ai.level = lvl
            self.custom_night_mode = True
        else:
            self.custom_night_mode = False
        self.state = "night_intro"
        self.intro_timer = 3.0

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (hasattr(pygame, "WINDOWCLOSE") and event.type == pygame.WINDOWCLOSE):
                self.confirm_quit = True
                self.confirm_action = "quit_app"
                continue
            if event.type == pygame.KEYDOWN:
                if self.confirm_quit:
                    if event.key in (pygame.K_y, pygame.K_RETURN):
                        self._confirm_yes()
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        self.confirm_quit = False
                    continue
                if event.key == pygame.K_ESCAPE:
                    if self.state == "playing":
                        self.confirm_quit = True
                        self.confirm_action = "abandon_night"
                    elif self.state == "menu":
                        self.confirm_quit = True
                        self.confirm_action = "quit_app"
                    elif self.state == "custom_night":
                        self.state = "menu"
                    elif self.state in ("gameover", "win_night", "win_game", "jumpscare"):
                        self.state = "menu"
                if self.state == "menu":
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        self.start_night(1)
                    elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8):
                        self.start_night(int(event.unicode))
                    elif event.key == pygame.K_c:
                        self.state = "custom_night"
                elif self.state == "custom_night":
                    if event.key == pygame.K_ESCAPE:
                        self.state = "menu"
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_UP:
                        self.custom_ai_level = min(20, self.custom_ai_level + 1)
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_DOWN:
                        self.custom_ai_level = max(0, self.custom_ai_level - 1)
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        self.start_night(7, ai_level=self.custom_ai_level)
                elif self.state == "playing" and not self.blackout:
                    if event.key == pygame.K_p:
                        self.paused = not self.paused
                        continue
                    if self.paused:
                        if event.key == pygame.K_m:
                            self.state = "menu"
                            self.paused = False
                        elif event.key == pygame.K_r:
                            if self.custom_night_mode:
                                self.start_night(7, ai_level=self.custom_ai_level)
                            else:
                                self.start_night(self.night)
                        continue
                    if event.key == pygame.K_h:
                        # toggle hiding (only when monitor is down)
                        if self.camera_up:
                            self.toast = "Close the monitor before hiding."
                            self.toast_timer = 1.5
                        else:
                            self.hiding = not self.hiding
                            self.hide_time_left = 30.0
                            self.toast = "Hiding under Liam's bed..." if self.hiding else "You crawled out from under the bed."
                            self.toast_timer = 1.2
                            self.play_sound("blip")
                            if self.hiding:
                                self.stats_hides += 1
                                self.left_light = False
                                self.right_light = False
                    if not self.hiding:
                        if event.key == pygame.K_SPACE:
                            self.camera_up = not self.camera_up
                            self.static_timer = 0.25
                            self.play_sound("camera")
                            self.stats_cam_toggles += 1
                        if event.key == pygame.K_q:
                            if self.left_door_cooldown > 0:
                                self.toast = f"Left door cooling down ({self.left_door_cooldown:.1f}s)"
                                self.toast_timer = 0.8
                            else:
                                self.left_door = not self.left_door
                                self.left_door_cooldown = 1.25
                                if self.left_door:
                                    self.left_door_close_timer = 10.0 if self.night == 5 else 20.0
                                else:
                                    self.left_door_close_timer = 0.0
                                self.play_sound("door")
                        if event.key == pygame.K_e:
                            if self.right_door_cooldown > 0:
                                self.toast = f"Right door cooling down ({self.right_door_cooldown:.1f}s)"
                                self.toast_timer = 0.8
                            else:
                                self.right_door = not self.right_door
                                self.right_door_cooldown = 1.25
                                if self.right_door:
                                    self.right_door_close_timer = 10.0 if self.night == 5 else 20.0
                                else:
                                    self.right_door_close_timer = 0.0
                                self.play_sound("door")
                        if event.key == pygame.K_a:
                            self.left_light = not self.left_light
                            if self.left_light:
                                self.right_light = False
                            self.ai.add_anger(0.5)
                            self.play_sound("blip")
                        if event.key == pygame.K_d:
                            self.right_light = not self.right_light
                            if self.right_light:
                                self.left_light = False
                            self.ai.add_anger(0.5)
                            self.play_sound("blip")
                        if self.camera_up:
                            cam_keys = {
                                pygame.K_1: "Jenifer's Bedroom",
                                pygame.K_2: "Upstairs Hall",
                                pygame.K_3: "Living Room",
                                pygame.K_4: "Dining Room",
                                pygame.K_5: "Bathroom",
                                pygame.K_6: "Kitchen",
                                pygame.K_7: "Left Hallway",
                                pygame.K_8: "Right Hallway",
                            }
                            if event.key in cam_keys:
                                self.current_cam = cam_keys[event.key]
                                self.static_timer = 0.15
                    else:
                        # limited actions while hiding
                        if event.key in (pygame.K_q, pygame.K_e, pygame.K_a, pygame.K_d, pygame.K_SPACE):
                            self.toast = "Can't do that while hiding. Press H to come out."
                            self.toast_timer = 1.2
                elif self.state == "cutscene_night5":
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                        self.state = "win_game"
                elif self.state in ("gameover", "win_night", "win_game", "jumpscare"):
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        if self.state == "win_night":
                            self.start_night(self.night + 1)
                        elif self.state == "win_game":
                            self.state = "menu"
                        elif self.state == "gameover":
                            self.start_night(self.night)
                        elif self.state == "jumpscare":
                            self.state = "gameover"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.confirm_quit:
                    self.handle_confirm_click(event.pos)
                else:
                    self.handle_click(event.pos)

    def _confirm_yes(self):
        if self.confirm_action == "abandon_night":
            self.confirm_quit = False
            self.state = "menu"
            return
        pygame.quit()
        sys.exit()

    def handle_confirm_click(self, pos):
        yes = self.ui.get("confirm_yes")
        no = self.ui.get("confirm_no")
        if yes and yes.collidepoint(pos):
            self._confirm_yes()
        elif no and no.collidepoint(pos):
            self.confirm_quit = False

    def handle_click(self, pos):
        if self.state == "menu":
            # click regions/buttons handled via UI if present; fallback start
            if self.ui.get("custom_btn") and self.ui["custom_btn"].collidepoint(pos):
                self.state = "custom_night"
            else:
                self.start_night(min(self.unlocked_night, self.max_night))
            return
        if self.state == "custom_night":
            if self.ui.get("cn_minus") and self.ui["cn_minus"].collidepoint(pos):
                self.custom_ai_level = max(0, self.custom_ai_level - 1)
            elif self.ui.get("cn_plus") and self.ui["cn_plus"].collidepoint(pos):
                self.custom_ai_level = min(20, self.custom_ai_level + 1)
            elif self.ui.get("cn_start") and self.ui["cn_start"].collidepoint(pos):
                self.start_night(7, ai_level=self.custom_ai_level)
            elif self.ui.get("cn_back") and self.ui["cn_back"].collidepoint(pos):
                self.state = "menu"
            return
        if self.state == "cutscene_night5":
            self.state = "win_game"
            return
        if self.state in ("gameover", "win_night", "win_game", "jumpscare"):
            if self.state == "win_night":
                if self.custom_night_mode or self.night >= self.max_night:
                    self.state = "menu"
                else:
                    self.start_night(self.night + 1)
            elif self.state == "win_game":
                self.state = "menu"
            elif self.state == "gameover":
                if self.custom_night_mode:
                    self.start_night(7, ai_level=self.custom_ai_level)
                else:
                    self.start_night(self.night)
            elif self.state == "jumpscare":
                self.state = "gameover"
            return
        if self.state != "playing" or self.blackout:
            return
        if self.paused:
            if self.ui.get("pause_resume") and self.ui["pause_resume"].collidepoint(pos):
                self.paused = False
            elif self.ui.get("pause_restart") and self.ui["pause_restart"].collidepoint(pos):
                if self.custom_night_mode:
                    self.start_night(7, ai_level=self.custom_ai_level)
                else:
                    self.start_night(self.night)
            elif self.ui.get("pause_menu") and self.ui["pause_menu"].collidepoint(pos):
                self.state = "menu"
                self.paused = False
            return
        # UI buttons
        if self.hiding:
            self.toast = "You're hiding. Press H to come out."
            self.toast_timer = 1.2
            return
        if self.ui.get("left_door") and self.ui["left_door"].collidepoint(pos):
            if self.left_door_cooldown > 0:
                self.toast = f"Left door cooling down ({self.left_door_cooldown:.1f}s)"
                self.toast_timer = 0.8
            else:
                self.left_door = not self.left_door
                self.left_door_cooldown = 1.25
                if self.left_door:
                    self.left_door_close_timer = 10.0 if self.night == 5 else 20.0
                else:
                    self.left_door_close_timer = 0.0
                self.play_sound("door")
        elif self.ui.get("right_door") and self.ui["right_door"].collidepoint(pos):
            if self.right_door_cooldown > 0:
                self.toast = f"Right door cooling down ({self.right_door_cooldown:.1f}s)"
                self.toast_timer = 0.8
            else:
                self.right_door = not self.right_door
                self.right_door_cooldown = 1.25
                if self.right_door:
                    self.right_door_close_timer = 10.0 if self.night == 5 else 20.0
                else:
                    self.right_door_close_timer = 0.0
                self.play_sound("door")
        elif self.ui.get("left_light") and self.ui["left_light"].collidepoint(pos):
            self.left_light = not self.left_light
            if self.left_light:
                self.right_light = False
            self.ai.add_anger(0.5)
        elif self.ui.get("right_light") and self.ui["right_light"].collidepoint(pos):
            self.right_light = not self.right_light
            if self.right_light:
                self.left_light = False
            self.ai.add_anger(0.5)
        elif self.ui.get("camera_toggle") and self.ui["camera_toggle"].collidepoint(pos):
            self.camera_up = not self.camera_up
            self.static_timer = 0.25
        elif self.camera_up:
            for name, rect in self.cam_buttons.items():
                if rect.collidepoint(pos):
                    self.current_cam = name
                    self.static_timer = 0.12
                    break

    def update(self, dt):
        if self.confirm_quit:
            return
        if self.state == "night_intro":
            self.intro_timer -= dt
            if self.intro_timer <= 0:
                self.state = "playing"
            return

        if self.state == "jumpscare":
            self.jumpscare_timer += dt
            if self.jumpscare_timer > 2.0:
                self.state = "gameover"
            return

        if self.state == "cutscene_night5":
            self.cutscene_timer += dt
            if self.cutscene_timer >= 14.0:
                self.state = "win_game"
            return

        if self.state != "playing":
            return

        if self.paused:
            return

        self.static_timer = max(0.0, self.static_timer - dt)
        self.message_timer = max(0.0, self.message_timer - dt)
        self.toast_timer = max(0.0, self.toast_timer - dt)
        self.ambience_timer = max(0.0, self.ambience_timer - dt)
        self.left_door_cooldown = max(0.0, self.left_door_cooldown - dt)
        self.right_door_cooldown = max(0.0, self.right_door_cooldown - dt)
        # hiding limit: 30 seconds per hide, then forced to come out
        if self.hiding:
            self.hide_time_left = max(0.0, self.hide_time_left - dt)
            if self.hide_time_left <= 0.0:
                self.hiding = False
                self.hide_time_left = 30.0
                self.toast = "You can't hide any longer - you came out!"
                self.toast_timer = 1.8
                self.play_sound("warn")
        # doors can only stay closed for a limited time, then auto-open
        if self.left_door:
            self.left_door_close_timer = max(0.0, self.left_door_close_timer - dt)
            if self.left_door_close_timer <= 0.0:
                self.left_door = False
                self.left_door_cooldown = max(self.left_door_cooldown, 0.5)
                self.toast = "Left door auto-opened!"
                self.toast_timer = 1.2
                self.play_sound("door")
        else:
            self.left_door_close_timer = 0.0
        if self.right_door:
            self.right_door_close_timer = max(0.0, self.right_door_close_timer - dt)
            if self.right_door_close_timer <= 0.0:
                self.right_door = False
                self.right_door_cooldown = max(self.right_door_cooldown, 0.5)
                self.toast = "Right door auto-opened!"
                self.toast_timer = 1.2
                self.play_sound("door")
        else:
            self.right_door_close_timer = 0.0
        # smooth animations
        door_speed = 4.5
        cam_speed = 6.0
        ltarget = 1.0 if self.left_door else 0.0
        rtarget = 1.0 if self.right_door else 0.0
        ctarget = 1.0 if (self.camera_up and not self.blackout and self.power > 0) else 0.0
        self.left_door_anim += (ltarget - self.left_door_anim) * min(1.0, dt * door_speed)
        self.right_door_anim += (rtarget - self.right_door_anim) * min(1.0, dt * door_speed)
        self.cam_anim += (ctarget - self.cam_anim) * min(1.0, dt * cam_speed)

        # Time
        self.time_elapsed += dt
        hour_idx = int(self.time_elapsed // HOUR_SECONDS)
        self.hour = 12 if hour_idx == 0 else hour_idx  # 12,1,2,3,4,5
        if self.hour != self.last_hour_mark:
            self.last_hour_mark = self.hour
            hourly = {
                1: "1 AM - The house creaks.",
                2: "2 AM - Something moved down the hall.",
                3: "3 AM - Stay focused.",
                4: "4 AM - Almost morning.",
                5: "5 AM - Just one more hour...",
            }
            if self.hour in hourly:
                self.ambience_msg = hourly[self.hour]
                self.ambience_timer = 2.5
        elif self.ambience_timer <= 0 and random.random() < dt * 0.08:
            flavor = [
                "You hear footsteps somewhere in the house...",
                "A floorboard creaks nearby.",
                "The wind rattles Jenifer's window.",
                "Something shifts in the hallway.",
            ]
            if self.dad.active and random.random() < 0.35:
                flavor.append("You hear Liam's dad mumbling in the house...")
            self.ambience_msg = random.choice(flavor)
            self.ambience_timer = 2.0

        if self.time_elapsed >= NIGHT_LENGTH_SECONDS:
            if not self.custom_night_mode:
                # Night 5 is the last story night; 6-8 are bonus nights (7 & 8 highlighted)
                if self.night < 5:
                    self.unlocked_night = max(self.unlocked_night, self.night + 1)
                elif self.night == 5:
                    self.unlocked_night = max(self.unlocked_night, 8)  # unlock all bonus rounds
                elif self.night == 6:
                    self.unlocked_night = max(self.unlocked_night, 8)
                elif self.night == 7:
                    self.unlocked_night = max(self.unlocked_night, 8)
                self.unlocked_night = min(self.unlocked_night, self.max_night)
                self.save_progress()
            self.night_summary = {
                "night": self.night,
                "power_left": int(self.power),
                "peak_anger": int(self.stats_peak_anger),
                "hides": self.stats_hides,
                "lectures": self.stats_lectures,
                "blocks": self.stats_door_blocks,
                "survived": self.stats_survived_encounters,
            }
            self.play_sound("win")
            if self.custom_night_mode:
                self.state = "win_game"
            elif self.night == 5:
                self.state = "cutscene_night5"  # story complete cutscene
                self.cutscene_timer = 0.0
            elif self.night >= self.max_night:
                self.state = "win_game"
            else:
                self.state = "win_night"
            return

        # Power usage: base 1 + devices
        usage = 1
        if self.left_door:
            usage += 1
        if self.right_door:
            usage += 1
        if self.left_light:
            usage += 1
        if self.right_light:
            usage += 1
        if self.camera_up:
            usage += 1
        self.usage = usage

        drain_per_sec = [0, 0.10, 0.16, 0.24, 0.34, 0.48, 0.65][clamp(usage, 0, 6)]
        if self.hiding:
            drain_per_sec *= 0.6  # quieter/lower activity while hiding
        if self.night >= 8 and not self.custom_night_mode:
            drain_per_sec *= 2.0  # Night 8: power drains much faster
        if not self.blackout:
            self.power -= drain_per_sec * dt
        if self.power <= 0 and not self.blackout:
            self.power = 0
            self.blackout = True
            self.blackout_timer = 0.0
            # Power out: everything off
            self.left_door = False
            self.right_door = False
            self.left_light = False
            self.right_light = False
            self.camera_up = False
            self.hiding = False
            self.message = "POWER OUT"
            self.message_timer = 99

        if self.blackout:
            self.blackout_timer += dt
            # tension delay, then guaranteed attack
            if self.blackout_timer > random.uniform(6.0, 12.0) + max(0, 3 - self.night):
                self.state = "jumpscare"
                self.jumpscare_timer = 0.0
            return

        # AI update
        prev_at_door = self.ai.location in ("Bedroom L Door", "Bedroom R Door")
        watched = self.camera_up and (self.ai.location == self.current_cam)
        self.ai.update(dt, self.left_door, self.right_door, player_hiding=self.hiding, watched=watched)
        self.stats_peak_anger = max(self.stats_peak_anger, self.ai.anger)
        if prev_at_door and self.ai.location not in ("Bedroom L Door", "Bedroom R Door"):
            # likely repelled/left; count as a successful block/holdout
            self.stats_door_blocks += 1
        # Liam's dad update
        prev_loc = self.ai.location
        dad_event = self.dad.update(dt, self.left_light, self.right_light, self.left_door, self.right_door, self.hiding, self.ai.anger)
        if dad_event in ("lecture_left", "lecture_right"):
            self.ai.add_anger(16.0)
            self.stats_lectures += 1
            lectures = [
                "Liam's dad lectured you for being up late... Jenifer got mad.",
                "Dad gave Liam a lecture. His mom heard and got angrier.",
                "Liam's dad caught you and lectured you — Jenifer is furious now.",
            ]
            self.toast = random.choice(lectures)
            self.toast_timer = 3.2
            self.play_sound("lecture")
        if self.ai.attack_pending:
            if self.hiding:
                # survive by hiding, but she gets angrier and moves away
                self.ai.attack_pending = False
                self.ai.add_anger(12.0)
                if self.ai.location == "Bedroom L Door":
                    self.ai.location = "Left Hallway"
                elif self.ai.location == "Bedroom R Door":
                    self.ai.location = "Right Hallway"
                self.ai.door_patience = 0.0
                self.toast = "You held your breath... she moved away angrier."
                self.toast_timer = 2.5
                self.stats_survived_encounters += 1
                self.play_sound("anger")
            else:
                self.state = "jumpscare"
                self.jumpscare_timer = 0.0
                self.play_sound("jumpscare")

    # --- Drawing helpers ---
    def draw_text(self, text, font, color, x, y, center=False, shadow=False):
        if shadow:
            sh = font.render(text, True, (0, 0, 0))
            sr = sh.get_rect()
            if center:
                sr.center = (x + 2, y + 2)
            else:
                sr.topleft = (x + 2, y + 2)
            self.screen.blit(sh, sr)
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if center:
            rect.center = (x, y)
        else:
            rect.topleft = (x, y)
        self.screen.blit(surf, rect)
        return rect

    def draw_vertical_gradient(self, rect, top_color, bottom_color):
        x, y, w, h = rect
        if h <= 0:
            return
        for i in range(h):
            t = i / max(1, h - 1)
            c = (
                int(top_color[0] + (bottom_color[0] - top_color[0]) * t),
                int(top_color[1] + (bottom_color[1] - top_color[1]) * t),
                int(top_color[2] + (bottom_color[2] - top_color[2]) * t),
            )
            pygame.draw.line(self.screen, c, (x, y + i), (x + w, y + i))

    def draw_vignette(self, strength=110):
        vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        cx, cy = WIDTH // 2, HEIGHT // 2
        maxd = math.hypot(cx, cy)
        step = 24
        for r in range(int(maxd), 0, -step):
            a = int(strength * (r / maxd) ** 1.8)
            if a <= 0:
                continue
            pygame.draw.circle(vignette, (0, 0, 0, min(255, a)), (cx, cy), r)
        self.screen.blit(vignette, (0, 0))

    def draw_menu(self):
        self.draw_vertical_gradient((0, 0, WIDTH, HEIGHT), (18, 12, 22), (3, 3, 6))
        # perspective grid floor
        vp = (WIDTH // 2, 260)
        for i in range(12):
            y = 360 + i * 34
            spread = 80 + i * 70
            pygame.draw.line(self.screen, (40, 20, 30), (vp[0] - spread, y), (vp[0] + spread, y), 1)
        for x in range(-6, 7):
            bx = WIDTH // 2 + x * 140
            pygame.draw.line(self.screen, (35, 18, 28), vp, (bx, HEIGHT), 1)
        # title glow
        self.draw_text("FIVE NIGHTS", self.title_font, (255, 80, 80), WIDTH // 2, 150, center=True)
        self.draw_text("FIVE NIGHTS", self.title_font, WHITE, WIDTH // 2, 146, center=True, shadow=True)
        self.draw_text("AT JENIFER'S HOUSE", self.title_font, (255, 40, 40), WIDTH // 2, 220, center=True, shadow=True)
        self.draw_text("You're house-sitting... but Ms. Jenifer roams at night.", self.small_font, (200, 170, 170), WIDTH // 2, 270, center=True)
        self.draw_text("Press ENTER or 1-8 to start a night", self.font, LIGHT_GRAY, WIDTH // 2, 345, center=True, shadow=True)
        extra = ""
        if self.unlocked_night >= 8:
            extra = " (Bonus rounds unlocked!)"
        elif self.unlocked_night >= 6:
            extra = " (Extra nights unlocked!)"
        self.draw_text(f"Unlocked: Night {min(self.unlocked_night,8)} / 8{extra}", self.small_font, GREEN, WIDTH // 2, 374, center=True)
        self.draw_text("Story: Nights 1-5  |  Bonus rounds: Nights 6-8", self.small_font, AMBER, WIDTH // 2, 398, center=True)
        self.draw_text("Controls (in Liam's room):", self.font, AMBER, WIDTH // 2, 420, center=True)
        lines = [
            "Q/E - Toggle Left/Right door",
            "A/D - Toggle Left/Right light",
            "SPACE - Open/Close camera monitor",
            "H - Hide under the bed / come out",
            "P - Pause game",
            "1-8 - Select camera (monitor open)",
            "ESC - Leave night/menu",
        ]
        for i, line in enumerate(lines):
            self.draw_text(line, self.small_font, (180, 180, 190), WIDTH // 2, 465 + i * 26, center=True)
        self.draw_text("Manage power, watch her anger, and hide when needed to survive.", self.small_font, LIGHT_GRAY, WIDTH // 2, 625, center=True)
        custom_rect = pygame.Rect(WIDTH // 2 - 110, 660, 220, 34)
        self.ui["custom_btn"] = custom_rect
        pygame.draw.rect(self.screen, (35, 28, 40), custom_rect, border_radius=6)
        pygame.draw.rect(self.screen, AMBER, custom_rect, 2, border_radius=6)
        self.draw_text("C / Click: Custom Night", self.small_font, AMBER, custom_rect.centerx, custom_rect.centery, center=True)
        self.draw_vignette(140)

    def draw_custom_night(self):
        self.draw_vertical_gradient((0, 0, WIDTH, HEIGHT), (14, 12, 20), (4, 4, 8))
        self.draw_text("CUSTOM NIGHT", self.title_font, WHITE, WIDTH // 2, 150, center=True, shadow=True)
        self.draw_text("Set Ms. Jenifer's AI level (0-20)", self.font, LIGHT_GRAY, WIDTH // 2, 230, center=True)
        self.draw_text(str(self.custom_ai_level), self.title_font, AMBER, WIDTH // 2, 330, center=True, shadow=True)
        labels = {0: "Inactive", 5: "Easy", 10: "Hard", 15: "Very Hard", 20: "Nightmare"}
        # nearest label
        nearest = min(labels.keys(), key=lambda k: abs(k - self.custom_ai_level))
        self.draw_text(labels[nearest], self.font, (200, 180, 180), WIDTH // 2, 390, center=True)

        minus = pygame.Rect(WIDTH // 2 - 180, 305, 60, 50)
        plus = pygame.Rect(WIDTH // 2 + 120, 305, 60, 50)
        start = pygame.Rect(WIDTH // 2 - 120, 460, 240, 44)
        back = pygame.Rect(WIDTH // 2 - 120, 520, 240, 38)
        for r, key in ((minus, "cn_minus"), (plus, "cn_plus"), (start, "cn_start"), (back, "cn_back")):
            self.ui[key] = r
            pygame.draw.rect(self.screen, (30, 30, 38), r, border_radius=8)
            pygame.draw.rect(self.screen, AMBER if key == "cn_start" else GRAY, r, 2, border_radius=8)
        self.draw_text("-", self.big_font, WHITE, minus.centerx, minus.centery - 2, center=True)
        self.draw_text("+", self.big_font, WHITE, plus.centerx, plus.centery - 2, center=True)
        self.draw_text("Start Custom Night", self.font, WHITE, start.centerx, start.centery, center=True)
        self.draw_text("Back (Esc)", self.small_font, LIGHT_GRAY, back.centerx, back.centery, center=True)
        self.draw_text("Left/Right arrows adjust, Enter to start", self.small_font, GRAY, WIDTH // 2, 590, center=True)
        self.draw_vignette(120)

    def draw_night_intro(self):
        self.draw_vertical_gradient((0, 0, WIDTH, HEIGHT), (8, 8, 12) if self.night < 8 else (20, 4, 8), (0, 0, 0))
        if self.night <= 5:
            night_label = f"Night {self.night}"
        elif self.night == 6:
            night_label = "Night 6 (Extra)"
        elif self.night == 7:
            night_label = "Night 7"
        else:
            night_label = "Night 8 (MONSTER)"
        self.draw_text(night_label, self.big_font, (255, 80, 80) if self.night >= 8 else WHITE, WIDTH // 2, HEIGHT // 2 - 60, center=True, shadow=True)
        self.draw_text("Jenifer's House - Liam's Room", self.font, (190, 170, 170), WIDTH // 2, HEIGHT // 2 - 15, center=True)
        self.draw_text("12:00 AM", self.font, GRAY, WIDTH // 2, HEIGHT // 2 + 18, center=True)
        stories = {
            1: "You're babysitting in Liam's room. Keep the doors ready.",
            2: "Liam's dad is home tonight. Don't let him catch you up late.",
            3: "Jenifer is restless. Watch your power and her anger.",
            4: "The house feels smaller. Every sound matters now.",
            5: "Final story night. Jenifer is at her worst - survive until morning.",
            6: "Bonus night: everyone is on edge. Good luck.",
            7: "Bonus round: the house feels wrong tonight...",
            8: "BONUS MONSTER ROUND: Jenifer has become a monster. Survive if you can.",
        }
        tips = {
            1: "Tip: Use lights to check hallways before opening doors.",
            2: "Tip: If Liam's dad appears, hide or close the door to avoid a lecture.",
            3: "Tip: Watching Jenifer and using lights can raise her anger.",
            4: "Tip: Hiding can save you in a close call, but makes her angrier.",
            5: "Tip: Doors auto-open after 10s closed. Time them carefully!",
            6: "Tip: Bonus night - doors auto-open after 20s closed.",
            7: "Tip: Bonus night - stay sharp and manage power.",
            8: "Tip: Bonus monster night - fast power drain, 20s door limit, extreme danger.",
        }
        self.draw_text(stories.get(self.night, stories[8]), self.small_font, (210, 200, 200) if self.night < 8 else (255, 120, 120), WIDTH // 2, HEIGHT // 2 + 58, center=True)
        self.draw_text(tips.get(self.night, tips[8]), self.small_font, (170, 170, 180), WIDTH // 2, HEIGHT // 2 + 86, center=True)
        self.draw_vignette(120)

    def _light_factor(self):
        # subtle flicker/pulse for alive feel
        t = pygame.time.get_ticks() * 0.001
        return 0.92 + 0.08 * math.sin(t * 2.3) + 0.03 * math.sin(t * 9.7)

    def draw_office(self):
        lf = self._light_factor()
        # base dark room
        self.draw_vertical_gradient((0, 0, WIDTH, HEIGHT), (16, 14, 20), (8, 8, 10))

        # 3D-ish perspective: ceiling, back wall, side walls, floor (Liam's room in Jenifer's house)
        ceil_color = (int(28 * lf), int(24 * lf), int(22 * lf))
        wall_color = (int(52 * lf), int(42 * lf), int(36 * lf))
        back_color = (int(46 * lf), int(38 * lf), int(34 * lf))
        floor_near = (int(72 * lf), int(55 * lf), int(40 * lf))
        floor_far = (int(40 * lf), int(32 * lf), int(26 * lf))

        # ceiling
        pygame.draw.polygon(self.screen, ceil_color, [(0, 0), (WIDTH, 0), (820, 170), (204, 170)])
        # back wall (receded)
        pygame.draw.polygon(self.screen, back_color, [(204, 170), (820, 170), (820, 470), (204, 470)])
        # left wall
        pygame.draw.polygon(self.screen, wall_color, [(0, 0), (204, 170), (204, 470), (0, 560)])
        # right wall
        pygame.draw.polygon(self.screen, (int(wall_color[0] * 0.9), int(wall_color[1] * 0.9), int(wall_color[2] * 0.9)),
                            [(WIDTH, 0), (820, 170), (820, 470), (WIDTH, 560)])
        # floor with perspective gradient bands
        for i in range(40):
            t = i / 39
            y1 = 470 + int(t * (HEIGHT - 470))
            y2 = 470 + int((i + 1) / 40 * (HEIGHT - 470))
            c = tuple(int(floor_far[j] + (floor_near[j] - floor_far[j]) * t) for j in range(3))
            inset = int((1 - t) * 204)
            pygame.draw.polygon(self.screen, c, [(inset, y1), (WIDTH - inset, y1), (WIDTH - int((1 - (i + 1) / 40) * 204), y2), (int((1 - (i + 1) / 40) * 204), y2)])
        # floor perspective lines
        for k in range(-5, 6):
            bx = WIDTH // 2 + k * 120
            pygame.draw.line(self.screen, (45, 38, 32), (WIDTH // 2, 470), (bx, HEIGHT), 1)

        # back wall details (window with curtains + picture frame) for house vibe
        # window
        pygame.draw.rect(self.screen, (18, 22, 35), (350, 210, 150, 150), border_radius=4)
        pygame.draw.rect(self.screen, (70, 80, 95), (350, 210, 150, 150), 3, border_radius=4)
        pygame.draw.line(self.screen, (70, 80, 95), (425, 210), (425, 360), 2)
        pygame.draw.line(self.screen, (70, 80, 95), (350, 285), (500, 285), 2)
        # curtains
        pygame.draw.rect(self.screen, (80, 35, 45), (340, 205, 28, 165), border_radius=3)
        pygame.draw.rect(self.screen, (80, 35, 45), (482, 205, 28, 165), border_radius=3)
        # picture frame
        pygame.draw.rect(self.screen, (70, 50, 35), (560, 230, 110, 120), border_radius=3)
        pygame.draw.rect(self.screen, (120, 90, 60), (560, 230, 110, 120), 3, border_radius=3)
        pygame.draw.rect(self.screen, (90, 70, 80), (572, 242, 86, 96))

        # desk in foreground with 3D faces
        desk_top = [(250, 500), (774, 500), (860, 590), (164, 590)]
        desk_front = [(164, 590), (860, 590), (860, 650), (164, 650)]
        desk_side_l = [(164, 590), (250, 500), (250, 560), (164, 650)]
        desk_side_r = [(860, 590), (774, 500), (774, 560), (860, 650)]
        pygame.draw.polygon(self.screen, (78, 58, 42), desk_top)
        pygame.draw.polygon(self.screen, (58, 42, 30), desk_front)
        pygame.draw.polygon(self.screen, (50, 36, 26), desk_side_l)
        pygame.draw.polygon(self.screen, (48, 35, 25), desk_side_r)
        pygame.draw.polygon(self.screen, (95, 72, 52), desk_top, 2)
        # monitor/fan on desk
        pygame.draw.rect(self.screen, (20, 22, 26), (450, 430, 120, 80), border_radius=4)
        pygame.draw.rect(self.screen, (80, 120, 140), (458, 438, 104, 64), border_radius=3)
        pygame.draw.rect(self.screen, (30, 30, 34), (500, 510, 20, 25))
        # fan
        pygame.draw.circle(self.screen, (40, 40, 44), (350, 470), 26)
        pygame.draw.circle(self.screen, (70, 70, 76), (350, 470), 26, 2)
        ang = pygame.time.get_ticks() * 0.02
        for k in range(3):
            a = ang + k * (math.tau / 3)
            pygame.draw.line(self.screen, (90, 90, 96), (350, 470), (350 + math.cos(a) * 20, 470 + math.sin(a) * 20), 3)

        # doorway geometry in perspective
        self.draw_doorway_3d(side="left")
        self.draw_doorway_3d(side="right")

        # ambient light cones when lights on
        if self.left_light and self.power > 0:
            cone = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(cone, (255, 230, 150, 35), [(120, 170), (230, 170), (320, 520), (40, 520)])
            self.screen.blit(cone, (0, 0))
        if self.right_light and self.power > 0:
            cone = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(cone, (255, 230, 150, 35), [(904, 170), (794, 170), (704, 520), (984, 520)])
            self.screen.blit(cone, (0, 0))

        # HUD
        hour_text = "12 AM" if self.hour == 12 else f"{self.hour} AM"
        hs = self.big_font.render(hour_text, True, WHITE)
        self.screen.blit(hs, (WIDTH - hs.get_width() - 30, 20))
        if self.night <= 5:
            night_label = f"Night {self.night}"
        elif self.night == 6:
            night_label = "Night 6 (Extra)"
        elif self.night == 7:
            night_label = "Night 7"
        else:
            night_label = "Night 8 (Monster)"
        ns = self.font.render(night_label, True, (255, 120, 120) if self.night >= 8 else LIGHT_GRAY)
        self.screen.blit(ns, (WIDTH - ns.get_width() - 30, 70))
        self.draw_text("Goal: 6 AM", self.small_font, GRAY, WIDTH - 30 - ns.get_width(), 100)
        # night progress bar
        prog = clamp(self.time_elapsed / NIGHT_LENGTH_SECONDS, 0.0, 1.0)
        bar_w = 160
        bx = WIDTH - bar_w - 30
        by = 122
        pygame.draw.rect(self.screen, (35, 35, 40), (bx, by, bar_w, 8), border_radius=4)
        pygame.draw.rect(self.screen, AMBER, (bx, by, int(bar_w * prog), 8), border_radius=4)
        pygame.draw.rect(self.screen, (90, 90, 100), (bx, by, bar_w, 8), 1, border_radius=4)

        pcol = GREEN if self.power > 50 else (YELLOW if self.power > 20 else RED)
        self.draw_text(f"Power: {int(self.power)}%", self.font, pcol, 30, 20, shadow=True)
        self.draw_text(f"Usage: {'|' * self.usage}", self.small_font, LIGHT_GRAY, 30, 50)
        # anger meter
        anger = int(self.ai.anger)
        acol = (120, 200, 120) if anger < 35 else (220, 200, 80) if anger < 70 else (230, 80, 80)
        self.draw_text(f"Jenifer Anger: {anger}%", self.small_font, acol, 30, 72, shadow=True)
        pygame.draw.rect(self.screen, (40, 40, 45), (30, 94, 180, 10), border_radius=3)
        pygame.draw.rect(self.screen, acol, (30, 94, int(180 * anger / 100), 10), border_radius=3)
        pygame.draw.rect(self.screen, (90, 90, 100), (30, 94, 180, 10), 1, border_radius=3)

        # proximity warning
        warn = None
        if self.ai.location in ("Left Hallway", "Bedroom L Door"):
            warn = "LEFT"
        elif self.ai.location in ("Right Hallway", "Bedroom R Door"):
            warn = "RIGHT"
        if warn and not self.blackout:
            pulse = 120 + int(80 * abs(math.sin(pygame.time.get_ticks() * 0.01)))
            self.draw_text(f"! MOTION: {warn} SIDE !", self.font, (255, pulse, pulse), WIDTH // 2, 85, center=True, shadow=True)
        if getattr(self, "dad", None) and self.dad.active and self.dad.location in ("Bedroom L Door", "Bedroom R Door", "Left Hallway", "Right Hallway"):
            side = "LEFT" if self.dad.location in ("Bedroom L Door", "Left Hallway") else "RIGHT"
            self.draw_text(f"Dad nearby ({side})", self.small_font, (255, 220, 120), 30, 112, shadow=True)

        cam_label = "H: Hide Under Bed  |  SPACE/CLICK: Monitor" if not self.hiding else "H: Come Out (Under Bed)"
        cam_rect = pygame.Rect(WIDTH // 2 - 190, HEIGHT - 48, 380, 34)
        self.ui["camera_toggle"] = cam_rect
        pygame.draw.rect(self.screen, (20, 24, 28), cam_rect, border_radius=6)
        pygame.draw.rect(self.screen, AMBER, cam_rect, 2, border_radius=6)
        self.draw_text(cam_label, self.small_font, AMBER, WIDTH // 2, HEIGHT - 31, center=True)

        # controls panel (clickable)
        if self.left_door_cooldown > 0:
            ldoor = f"Q Door CD {self.left_door_cooldown:.1f}s"
        elif self.left_door:
            ldoor = f"Q Door {self.left_door_close_timer:.0f}s"
        else:
            ldoor = "Q Door"
        if self.right_door_cooldown > 0:
            rdoor = f"E Door CD {self.right_door_cooldown:.1f}s"
        elif self.right_door:
            rdoor = f"E Door {self.right_door_close_timer:.0f}s"
        else:
            rdoor = "E Door"
        self.draw_button_hint(18, 565, ldoor, self.left_door, key="left_door")
        self.draw_button_hint(18, 600, "A Light", self.left_light, key="left_light")
        self.draw_button_hint(WIDTH - 123, 565, rdoor, self.right_door, key="right_door")
        self.draw_button_hint(WIDTH - 123, 600, "D Light", self.right_light, key="right_light")

        if self.power <= 0:
            self.draw_text("POWER OUT - She's in the house...", self.font, RED, WIDTH // 2, 120, center=True, shadow=True)

        if self.ambience_timer > 0 and self.ambience_msg:
            self.draw_text(self.ambience_msg, self.small_font, (200, 200, 210), WIDTH // 2, 145, center=True, shadow=True)
        if self.toast_timer > 0 and self.toast:
            tw = self.small_font.render(self.toast, True, WHITE)
            tr = tw.get_rect(center=(WIDTH // 2, 170))
            bg = tr.inflate(20, 12)
            pygame.draw.rect(self.screen, (20, 20, 26), bg, border_radius=6)
            pygame.draw.rect(self.screen, AMBER, bg, 1, border_radius=6)
            self.screen.blit(tw, tr)

        # danger atmosphere
        danger = 0.0
        if self.ai.location in ("Bedroom L Door", "Bedroom R Door"):
            danger = max(danger, 0.6)
        elif self.ai.location in ("Left Hallway", "Right Hallway"):
            danger = max(danger, 0.35)
        danger = max(danger, min(0.5, self.ai.anger / 200.0))
        if danger > 0:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.008)
            dv = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            dv.fill((140, 20, 20, int(20 + 45 * danger * pulse)))
            self.screen.blit(dv, (0, 0))
        self.draw_vignette(120 + int(40 * danger))

    def draw_doorway_3d(self, side="left"):
        if side == "left":
            outer = [(0, 120), (170, 170), (170, 500), (0, 560)]
            inner = [(20, 160), (150, 190), (150, 485), (20, 525)]
            hall_col_lit = (95, 85, 60)
            hall_col_dark = (12, 12, 18)
            light_on = self.left_light and self.power > 0
            door_closed = self.left_door
            at_door = self.ai.location == "Bedroom L Door"
            figure_pos = (85, 360)
            door_poly = [(24, 160), (146, 190), (146, 485), (24, 525)]
            frame_col = (70, 70, 80)
        else:
            outer = [(WIDTH, 120), (WIDTH - 170, 170), (WIDTH - 170, 500), (WIDTH, 560)]
            inner = [(WIDTH - 20, 160), (WIDTH - 150, 190), (WIDTH - 150, 485), (WIDTH - 20, 525)]
            hall_col_lit = (95, 85, 60)
            hall_col_dark = (12, 12, 18)
            light_on = self.right_light and self.power > 0
            door_closed = self.right_door
            at_door = self.ai.location == "Bedroom R Door"
            figure_pos = (WIDTH - 85, 360)
            door_poly = [(WIDTH - 24, 160), (WIDTH - 146, 190), (WIDTH - 146, 485), (WIDTH - 24, 525)]
            frame_col = (62, 62, 72)

        pygame.draw.polygon(self.screen, (28, 28, 34), outer)
        pygame.draw.polygon(self.screen, hall_col_lit if light_on else hall_col_dark, inner)
        pygame.draw.polygon(self.screen, frame_col, outer, 4)
        pygame.draw.polygon(self.screen, (90, 90, 100), inner, 2)

        # hall depth lines
        if light_on:
            c = (120, 105, 70)
            if side == "left":
                for i in range(4):
                    x = 35 + i * 28
                    pygame.draw.line(self.screen, c, (x, 200 + i * 8), (x, 470 - i * 8), 1)
            else:
                for i in range(4):
                    x = WIDTH - 35 - i * 28
                    pygame.draw.line(self.screen, c, (x, 200 + i * 8), (x, 470 - i * 8), 1)

        dad_at_door = getattr(self, "dad", None) and self.dad.active and (
            (side == "left" and self.dad.location == "Bedroom L Door") or
            (side == "right" and self.dad.location == "Bedroom R Door")
        )
        if light_on and at_door:
            self.draw_jenifer_silhouette(figure_pos[0], figure_pos[1], danger=True, scale=1.1)
        elif light_on and dad_at_door:
            self.draw_dad_figure(figure_pos[0], figure_pos[1], scale=1.05)
            self.draw_text("Liam's Dad is here - hide or close the door!", self.small_font, (255, 220, 120), WIDTH // 2, 115, center=True, shadow=True)

        anim = self.left_door_anim if side == "left" else self.right_door_anim
        if anim > 0.01:
            # metallic 3D door slab sliding down
            pts = door_poly
            top_y = [pts[0][1], pts[1][1]]
            bot_y = [pts[3][1], pts[2][1]]
            span0 = bot_y[0] - top_y[0]
            span1 = bot_y[1] - top_y[1]
            cur = anim
            dpts = [
                (pts[0][0], int(top_y[0])),
                (pts[1][0], int(top_y[1])),
                (pts[2][0], int(top_y[1] + span1 * cur)),
                (pts[3][0], int(top_y[0] + span0 * cur)),
            ]
            pygame.draw.polygon(self.screen, (72, 74, 82), dpts)
            for i in range(7):
                t = i / 6
                if t > cur:
                    break
                y_top = int(dpts[0][1] + (dpts[3][1] - dpts[0][1]) * t)
                xL = int(dpts[0][0] + (dpts[3][0] - dpts[0][0]) * t)
                xR = int(dpts[1][0] + (dpts[2][0] - dpts[1][0]) * t)
                shade = 90 + (i % 2) * 20
                pygame.draw.line(self.screen, (shade, shade, shade + 8), (xL + 6, y_top), (xR - 6, y_top), 2)
            pygame.draw.polygon(self.screen, (120, 122, 135), dpts, 2)
            if cur > 0.95:
                if side == "left":
                    edge = [(146, 190), (158, 198), (158, 493), (146, 485)]
                else:
                    edge = [(WIDTH - 146, 190), (WIDTH - 158, 198), (WIDTH - 158, 493), (WIDTH - 146, 485)]
                pygame.draw.polygon(self.screen, (45, 46, 52), edge)

    def draw_button_hint(self, x, y, label, active, key=None):
        rect = pygame.Rect(x, y, 105, 28)
        if key:
            self.ui[key] = rect
        col = GREEN if active else (90, 90, 100)
        bg = (40, 60, 45) if active else (28, 28, 34)
        pygame.draw.rect(self.screen, bg, rect, border_radius=5)
        pygame.draw.rect(self.screen, col, rect, 2, border_radius=5)
        self.draw_text(label, self.small_font, WHITE if active else LIGHT_GRAY, x + 8, y + 4)
        return rect

    def draw_jenifer_silhouette(self, cx, cy, danger=False, scale=1.0):
        # Ms. Jenifer: woman-like figure (or monster form on Night 8)
        def S(v):
            return int(v * scale)

        monster = (getattr(self, "night", 1) >= 8 and not getattr(self, "custom_night_mode", False))
        if monster:
            # Monster Jenifer
            skin = (90, 40, 55)
            skin_sh = (60, 25, 35)
            skin_hi = (130, 60, 75)
            hair = (20, 8, 18)
            hair_hi = (60, 15, 35)
            dress = (35, 10, 20)
            dress_hi = (80, 20, 35)
            accent = (180, 30, 50)
            eye_c = (255, 40, 40)
            iris = (255, 120, 0)
            lip = (120, 20, 30)
            scale = scale * 1.08
        else:
            hair = (16, 10, 20) if not danger else (45, 12, 22)
            hair_hi = (40, 28, 45) if not danger else (85, 22, 35)
            skin = (214, 184, 168) if not danger else (198, 155, 150)
            skin_sh = (178, 146, 132) if not danger else (155, 118, 116)
            skin_hi = (235, 210, 196) if not danger else (220, 185, 178)
            dress = (52, 28, 62) if not danger else (78, 22, 40)
            dress_hi = (78, 45, 92) if not danger else (120, 40, 62)
            accent = (170, 130, 185) if not danger else (210, 70, 90)
            eye_c = (255, 80, 80) if danger else (245, 248, 255)
            iris = (120, 30, 40) if danger else (90, 120, 170)
            lip = (165, 70, 90) if not danger else (175, 45, 60)

        # shadow
        shadow = pygame.Surface((S(260), S(320)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 140), (S(40), S(235), S(180), S(50)))
        self.screen.blit(shadow, (cx - S(130), cy - S(150)))

        # dress/skirt with folds
        skirt = [
            (cx - S(24), cy - S(12)),
            (cx + S(24), cy - S(12)),
            (cx + S(60), cy + S(125)),
            (cx - S(60), cy + S(125)),
        ]
        pygame.draw.polygon(self.screen, dress, skirt)
        for i, dx in enumerate((-18, 0, 18)):
            x1 = cx + S(dx // 2)
            pygame.draw.line(self.screen, dress_hi, (x1, cy - S(8)), (cx + S(dx), cy + S(120)), 2)
        pygame.draw.polygon(self.screen, dress_hi, skirt, 2)
        if monster:
            # claws/tendrils hint
            pygame.draw.line(self.screen, (80, 20, 30), (cx - S(55), cy + S(110)), (cx - S(80), cy + S(140)), 4)
            pygame.draw.line(self.screen, (80, 20, 30), (cx + S(55), cy + S(110)), (cx + S(80), cy + S(140)), 4)

        # torso/blouse with shading
        torso = [(cx - S(26), cy - S(56)), (cx + S(26), cy - S(56)), (cx + S(22), cy - S(2)), (cx - S(22), cy - S(2))]
        pygame.draw.polygon(self.screen, (85, 72, 96), torso)
        pygame.draw.polygon(self.screen, (105, 90, 118), [(cx - S(8), cy - S(52)), (cx + S(10), cy - S(52)), (cx + S(8), cy - S(6)), (cx - S(6), cy - S(6))])
        pygame.draw.polygon(self.screen, accent, torso, 2)
        pygame.draw.arc(self.screen, accent, (cx - S(16), cy - S(60), S(32), S(20)), 3.25, 6.15, 2)
        # pendant/detail
        pygame.draw.circle(self.screen, (220, 210, 180), (cx, cy - S(44)), S(3))

        # arms with shading
        for side in (-1, 1):
            sx = cx + side * S(24)
            ex = cx + side * S(48)
            pygame.draw.line(self.screen, skin_sh, (sx, cy - S(46)), (ex, cy + S(12)), S(9))
            pygame.draw.line(self.screen, skin, (sx - side*S(1), cy - S(46)), (ex - side*S(2), cy + S(10)), S(6))
            pygame.draw.circle(self.screen, skin, (ex, cy + S(12)), S(5))

        # neck
        pygame.draw.rect(self.screen, skin, (cx - S(8), cy - S(74), S(16), S(20)), border_radius=S(5))
        pygame.draw.rect(self.screen, skin_sh, (cx - S(8), cy - S(74), S(16), S(20)), 1, border_radius=S(5))

        # long hair back
        hair_back = [
            (cx - S(36), cy - S(92)),
            (cx + S(36), cy - S(92)),
            (cx + S(46), cy - S(24)),
            (cx + S(32), cy + S(10)),
            (cx - S(32), cy + S(10)),
            (cx - S(46), cy - S(24)),
        ]
        pygame.draw.polygon(self.screen, hair, hair_back)
        for dx in (-22, -8, 8, 22):
            x1 = cx + S(dx)
            x2 = cx + S(dx * 1.25)
            pygame.draw.line(self.screen, hair_hi, (x1, cy - S(86)), (int(x2), cy + S(2)), 2)
        pygame.draw.polygon(self.screen, hair_hi, hair_back, 2)

        # head and face shading
        face_rect = (cx - S(23), cy - S(100), S(46), S(54))
        pygame.draw.ellipse(self.screen, skin, face_rect)
        pygame.draw.ellipse(self.screen, skin_hi, (cx - S(16), cy - S(96), S(18), S(28)))
        pygame.draw.ellipse(self.screen, skin_sh, face_rect, 2)
        # cheeks
        blush = pygame.Surface((S(14), S(8)), pygame.SRCALPHA)
        pygame.draw.ellipse(blush, (220, 140, 150, 35 if not danger else 20), (0, 0, S(14), S(8)))
        self.screen.blit(blush, (cx - S(20), cy - S(66)))
        self.screen.blit(blush, (cx + S(6), cy - S(66)))

        # bangs/hair top
        bangs = [(cx - S(25), cy - S(94)), (cx + S(25), cy - S(94)), (cx + S(21), cy - S(74)), (cx + S(9), cy - S(84)), (cx, cy - S(70)), (cx - S(9), cy - S(84)), (cx - S(21), cy - S(74))]
        pygame.draw.polygon(self.screen, hair, bangs)
        for dx in (-14, -4, 6, 16):
            pygame.draw.line(self.screen, hair_hi, (cx + S(dx), cy - S(93)), (cx + S(dx - 4), cy - S(75)), 2)

        # monster horns/details
        if monster:
            pygame.draw.polygon(self.screen, (60, 20, 30), [(cx - S(18), cy - S(96)), (cx - S(34), cy - S(130)), (cx - S(8), cy - S(102))])
            pygame.draw.polygon(self.screen, (60, 20, 30), [(cx + S(18), cy - S(96)), (cx + S(34), cy - S(130)), (cx + S(8), cy - S(102))])
            pygame.draw.polygon(self.screen, (120, 40, 50), [(cx - S(18), cy - S(96)), (cx - S(30), cy - S(124)), (cx - S(10), cy - S(100))], 2)
            pygame.draw.polygon(self.screen, (120, 40, 50), [(cx + S(18), cy - S(96)), (cx + S(30), cy - S(124)), (cx + S(10), cy - S(100))], 2)

        # eyes with more detail
        for ex in (-S(9), S(9)):
            ew, eh = (S(16), S(10)) if monster else (S(14), S(8))
            er = (cx + ex - ew // 2, cy - S(81), ew, eh)
            pygame.draw.ellipse(self.screen, (248, 248, 248) if not monster else (255, 230, 230), er)
            pygame.draw.circle(self.screen, iris, (cx + ex, cy - S(76)), S(5) if monster else S(4))
            pygame.draw.circle(self.screen, eye_c, (cx + ex, cy - S(76)), S(3) if monster else S(2))
            pygame.draw.circle(self.screen, (15, 10, 10), (cx + ex + S(1), cy - S(76)), S(2) if monster else S(1))
            pygame.draw.circle(self.screen, (255, 255, 255), (cx + ex - S(2), cy - S(78)), S(1))
            pygame.draw.arc(self.screen, (35, 22, 30), (cx + ex - S(9), cy - S(84), S(18), S(14)), 0.15, 2.95, 2)
            if danger or monster:
                glow = pygame.Surface((S(22), S(14)), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (255, 60, 60, 55 if monster else 45), (0, 0, S(22), S(14)))
                self.screen.blit(glow, (cx + ex - S(11), cy - S(83)))
        # brows, nose, lips
        brow_col = (70, 20, 30) if monster else (45, 30, 35)
        pygame.draw.arc(self.screen, brow_col, (cx - S(19), cy - S(90), S(15), S(8)), 0.2, 2.9, 3 if monster else 2)
        pygame.draw.arc(self.screen, brow_col, (cx + S(4), cy - S(90), S(15), S(8)), 0.25, 2.95, 3 if monster else 2)
        pygame.draw.line(self.screen, skin_sh, (cx, cy - S(72)), (cx - S(2), cy - S(65)), 2)
        if monster:
            pygame.draw.arc(self.screen, (140, 20, 30), (cx - S(10), cy - S(63), S(20), S(12)), 3.2, 6.08, 3)
            for tx in (-6, 0, 6):
                pygame.draw.line(self.screen, (230, 230, 220), (cx + S(tx), cy - S(59)), (cx + S(tx), cy - S(54)), 2)
        else:
            pygame.draw.line(self.screen, lip, (cx - S(7), cy - S(59)), (cx + S(7), cy - S(59)), 2)
            pygame.draw.arc(self.screen, lip, (cx - S(7), cy - S(61), S(14), S(7)), 3.25, 6.05, 2)

        # subtle highlight
        hl = pygame.Surface((S(20), S(34)), pygame.SRCALPHA)
        pygame.draw.ellipse(hl, (255, 255, 255, 30), (0, 0, S(20), S(34)))
        self.screen.blit(hl, (cx - S(17), cy - S(94)))

    def draw_dad_figure(self, cx, cy, scale=1.0):
        # Liam's dad - improved procedural look
        def S(v):
            return int(v * scale)
        skin = (198, 168, 148)
        skin_sh = (165, 136, 120)
        skin_hi = (220, 195, 178)
        hair = (60, 48, 42)
        hair_hi = (85, 70, 62)
        shirt = (58, 82, 115)
        shirt_hi = (82, 110, 148)
        pants = (48, 50, 58)

        shadow = pygame.Surface((S(210), S(270)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 110), (S(35), S(210), S(145), S(38)))
        self.screen.blit(shadow, (cx - S(105), cy - S(135)))

        # legs
        pygame.draw.rect(self.screen, pants, (cx - S(23), cy + S(12), S(20), S(98)), border_radius=S(6))
        pygame.draw.rect(self.screen, pants, (cx + S(3), cy + S(12), S(20), S(98)), border_radius=S(6))
        pygame.draw.line(self.screen, (70, 72, 82), (cx - S(13), cy + S(20)), (cx - S(13), cy + S(105)), 2)
        pygame.draw.line(self.screen, (70, 72, 82), (cx + S(13), cy + S(20)), (cx + S(13), cy + S(105)), 2)
        # shoes
        pygame.draw.ellipse(self.screen, (35, 32, 30), (cx - S(30), cy + S(100), S(30), S(14)))
        pygame.draw.ellipse(self.screen, (35, 32, 30), (cx, cy + S(100), S(30), S(14)))

        # torso
        pygame.draw.rect(self.screen, shirt, (cx - S(30), cy - S(46), S(60), S(68)), border_radius=S(9))
        pygame.draw.rect(self.screen, shirt_hi, (cx - S(10), cy - S(42), S(18), S(58)), border_radius=S(6))
        pygame.draw.polygon(self.screen, shirt_hi, [(cx - S(10), cy - S(46)), (cx + S(10), cy - S(46)), (cx, cy - S(22))], 2)
        # belt
        pygame.draw.rect(self.screen, (45, 35, 30), (cx - S(28), cy + S(10), S(56), S(8)), border_radius=2)

        # arms and hands
        for side in (-1, 1):
            sx = cx + side * S(30)
            ex = cx + side * S(50)
            pygame.draw.line(self.screen, shirt, (sx, cy - S(32)), (ex, cy + S(18)), S(11))
            pygame.draw.line(self.screen, shirt_hi, (sx, cy - S(32)), (ex + side*S(-2), cy + S(14)), S(5))
            pygame.draw.circle(self.screen, skin, (ex, cy + S(18)), S(6))

        # neck/head
        pygame.draw.rect(self.screen, skin, (cx - S(9), cy - S(64), S(18), S(20)), border_radius=S(5))
        face = (cx - S(23), cy - S(100), S(46), S(48))
        pygame.draw.ellipse(self.screen, skin, face)
        pygame.draw.ellipse(self.screen, skin_hi, (cx - S(15), cy - S(96), S(16), S(22)))
        pygame.draw.ellipse(self.screen, skin_sh, face, 2)
        # hair (receding)
        pygame.draw.arc(self.screen, hair, (cx - S(24), cy - S(104), S(48), S(32)), 0.25, 2.9, S(7))
        pygame.draw.arc(self.screen, hair_hi, (cx - S(20), cy - S(102), S(40), S(20)), 0.5, 2.6, 2)
        # ears
        pygame.draw.ellipse(self.screen, skin, (cx - S(27), cy - S(84), S(7), S(14)))
        pygame.draw.ellipse(self.screen, skin, (cx + S(20), cy - S(84), S(7), S(14)))
        # eyes/brows
        for ex in (-S(8), S(8)):
            pygame.draw.ellipse(self.screen, (240, 240, 240), (cx + ex - S(5), cy - S(82), S(10), S(6)))
            pygame.draw.circle(self.screen, (70, 85, 105), (cx + ex, cy - S(79)), S(2))
            pygame.draw.circle(self.screen, (20, 20, 20), (cx + ex, cy - S(79)), S(1))
        pygame.draw.line(self.screen, hair, (cx - S(14), cy - S(87)), (cx - S(3), cy - S(86)), 2)
        pygame.draw.line(self.screen, hair, (cx + S(3), cy - S(86)), (cx + S(14), cy - S(87)), 2)
        # nose/mouth
        pygame.draw.line(self.screen, skin_sh, (cx, cy - S(75)), (cx - S(3), cy - S(68)), 2)
        pygame.draw.arc(self.screen, (130, 95, 90), (cx - S(8), cy - S(68), S(16), S(10)), 3.4, 6.0, 2)

    def draw_camera(self, anim=1.0):
        # Camera monitor overlay (fade with animation)
        a = int(60 * clamp(anim, 0.0, 1.0))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, a))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(70, 50, WIDTH - 140, HEIGHT - 120)
        pygame.draw.rect(self.screen, (14, 18, 16), panel, border_radius=8)
        pygame.draw.rect(self.screen, (60, 110, 80), panel, 3, border_radius=8)
        inner = panel.inflate(-18, -18)
        pygame.draw.rect(self.screen, (8, 12, 10), inner, border_radius=6)

        # Camera view area with pseudo-3D room
        view = pygame.Rect(100, 85, 580, 380)
        pygame.draw.rect(self.screen, (5, 8, 7), view)
        # perspective room inside camera
        vp = (view.centerx, view.top + 110)
        back = pygame.Rect(view.centerx - 120, view.top + 110, 240, 150)
        pygame.draw.polygon(self.screen, (18, 24, 22), [(view.left, view.top), (view.right, view.top), (back.right, back.top), (back.left, back.top)])  # ceiling
        pygame.draw.polygon(self.screen, (22, 28, 26), [(view.left, view.bottom), (view.right, view.bottom), (back.right, back.bottom), (back.left, back.bottom)])  # floor
        pygame.draw.polygon(self.screen, (20, 26, 24), [(view.left, view.top), (back.left, back.top), (back.left, back.bottom), (view.left, view.bottom)])  # left wall
        pygame.draw.polygon(self.screen, (16, 22, 20), [(view.right, view.top), (back.right, back.top), (back.right, back.bottom), (view.right, view.bottom)])  # right wall
        pygame.draw.rect(self.screen, (14, 20, 18), back)  # back wall
        # grid lines for depth
        for i in range(1, 6):
            t = i / 6
            y = back.bottom + int((view.bottom - back.bottom) * t)
            lx = back.left - int((back.left - view.left) * t)
            rx = back.right + int((view.right - back.right) * t)
            pygame.draw.line(self.screen, (30, 40, 34), (lx, y), (rx, y), 1)
        for k in range(-3, 4):
            bx = back.centerx + k * 35
            fx = view.centerx + k * 90
            pygame.draw.line(self.screen, (28, 36, 32), (bx, back.bottom), (fx, view.bottom), 1)

        pygame.draw.rect(self.screen, (60, 100, 70), view, 2)

        # Static/noise overlay
        if self.static_timer > 0 or random.random() < 0.04:
            noise = pygame.Surface((view.width, view.height), pygame.SRCALPHA)
            dots = 220 if self.static_timer > 0 else 80
            for _ in range(dots):
                x = random.randint(0, view.width - 2)
                y = random.randint(0, view.height - 2)
                a = random.randint(30, 90)
                c = random.randint(60, 180)
                pygame.draw.rect(noise, (c, c, c, a), (x, y, 2, 2))
            self.screen.blit(noise, view.topleft)
        # scanlines
        scan = pygame.Surface((view.width, view.height), pygame.SRCALPHA)
        for y in range(0, view.height, 4):
            pygame.draw.line(scan, (0, 0, 0, 35), (0, y), (view.width, y), 1)
        self.screen.blit(scan, view.topleft)

        self.draw_text(f"CAM: {self.current_cam}", self.small_font, (120, 255, 140), view.left + 10, view.top + 10, shadow=True)
        if int(pygame.time.get_ticks() / 500) % 2 == 0:
            pygame.draw.circle(self.screen, RED, (view.right - 20, view.top + 18), 5)
            self.draw_text("REC", self.small_font, RED, view.right - 55, view.top + 8)

        # Presence
        bob = math.sin(pygame.time.get_ticks() * 0.004) * 4
        jen_here = self.ai.location == self.current_cam
        dad_here = getattr(self, "dad", None) and self.dad.active and self.dad.location == self.current_cam
        if jen_here and dad_here:
            self.draw_jenifer_silhouette(view.centerx - 60, view.centery + 65 + int(bob), danger=True, scale=1.05)
            self.draw_dad_figure(view.centerx + 70, view.centery + 70, scale=1.0)
            self.draw_text("MOTION: MS. JENIFER + LIAM'S DAD", self.small_font, RED, view.left + 10, view.bottom - 28, shadow=True)
        elif jen_here:
            self.draw_jenifer_silhouette(view.centerx, view.centery + 65 + int(bob), danger=True, scale=1.25)
            self.draw_text("MOTION DETECTED: MS. JENIFER", self.small_font, RED, view.left + 10, view.bottom - 28, shadow=True)
        elif dad_here:
            self.draw_dad_figure(view.centerx, view.centery + 70, scale=1.15)
            self.draw_text("MOTION DETECTED: LIAM'S DAD", self.small_font, (255, 220, 120), view.left + 10, view.bottom - 28, shadow=True)
        else:
            self.draw_text("No movement detected", self.small_font, (170, 180, 170), view.left + 10, view.bottom - 28)
            # room-specific props in 3D space (house vibe)
            if self.current_cam == "Kitchen":
                pygame.draw.rect(self.screen, (45, 45, 48), (view.centerx - 170, view.bottom - 110, 160, 60))
                pygame.draw.rect(self.screen, (70, 70, 75), (view.centerx - 170, view.bottom - 110, 160, 60), 2)
                for i in range(3):
                    pygame.draw.rect(self.screen, (55, 58, 62), (view.centerx - 150 + i*50, view.bottom - 150, 36, 35), 2)
                pygame.draw.circle(self.screen, (90, 90, 95), (view.centerx + 40, view.bottom - 130), 12, 2)
            elif self.current_cam == "Living Room":
                pygame.draw.rect(self.screen, (55, 40, 35), (view.centerx - 160, view.bottom - 115, 170, 55), border_radius=6)
                pygame.draw.rect(self.screen, (75, 55, 45), (view.centerx - 160, view.bottom - 145, 170, 35), border_radius=6)
                pygame.draw.rect(self.screen, (30, 28, 32), (view.centerx + 60, view.bottom - 170, 70, 45), 2) # TV
            elif self.current_cam == "Jenifer's Bedroom":
                pygame.draw.rect(self.screen, (60, 45, 55), (view.centerx - 130, view.bottom - 120, 180, 50), border_radius=4)
                pygame.draw.rect(self.screen, (90, 80, 85), (view.centerx - 110, view.bottom - 150, 140, 35), border_radius=4)
                pygame.draw.rect(self.screen, (50, 45, 40), (view.centerx + 70, view.bottom - 165, 40, 60), 2) # lamp
            elif self.current_cam == "Bathroom":
                pygame.draw.rect(self.screen, (70, 75, 80), (view.centerx - 70, view.bottom - 135, 100, 75), border_radius=8)
                pygame.draw.rect(self.screen, (120, 130, 140), (view.centerx - 70, view.bottom - 135, 100, 75), 2, border_radius=8)
                pygame.draw.rect(self.screen, (90, 95, 100), (view.centerx + 60, view.bottom - 170, 50, 70), 2) # mirror/cabinet
            elif self.current_cam == "Dining Room":
                pygame.draw.ellipse(self.screen, (70, 50, 35), (view.centerx - 90, view.bottom - 135, 180, 60))
                pygame.draw.ellipse(self.screen, (95, 70, 50), (view.centerx - 90, view.bottom - 135, 180, 60), 2)
                for dx in (-70, 70):
                    pygame.draw.rect(self.screen, (60, 45, 35), (view.centerx + dx - 10, view.bottom - 150, 20, 20), 2)
            elif self.current_cam == "Upstairs Hall":
                pygame.draw.rect(self.screen, (60, 50, 45), (view.centerx - 160, view.bottom - 160, 40, 110), 2) # door frame
                pygame.draw.rect(self.screen, (60, 50, 45), (view.centerx + 120, view.bottom - 160, 40, 110), 2)
                pygame.draw.rect(self.screen, (80, 70, 50), (view.centerx - 30, view.bottom - 155, 60, 80), 2) # picture
            elif self.current_cam in ("Left Hallway", "Right Hallway"):
                pygame.draw.rect(self.screen, (45, 40, 38), (view.centerx - 120, view.bottom - 170, 30, 120), 2)
                pygame.draw.rect(self.screen, (45, 40, 38), (view.centerx + 90, view.bottom - 170, 30, 120), 2)
                pygame.draw.line(self.screen, (60, 55, 50), (view.centerx - 40, view.bottom - 150), (view.centerx + 40, view.bottom - 150), 2)
            else:
                pygame.draw.rect(self.screen, (30, 36, 34), (view.centerx - 140, view.bottom - 120, 90, 70))
                pygame.draw.polygon(self.screen, (26, 32, 30), [(view.centerx - 140, view.bottom - 120), (view.centerx - 120, view.bottom - 145), (view.centerx - 30, view.bottom - 145), (view.centerx - 50, view.bottom - 120)])
                pygame.draw.rect(self.screen, (35, 40, 38), (view.centerx + 50, view.bottom - 140, 70, 90), 2)

        # Map panel
        map_rect = pygame.Rect(700, 100, 220, 360)
        pygame.draw.rect(self.screen, (8, 12, 10), map_rect, border_radius=6)
        pygame.draw.rect(self.screen, (60, 100, 70), map_rect, 2, border_radius=6)
        self.draw_text("SITE MAP [1-8]", self.small_font, (120, 255, 140), map_rect.left + 10, map_rect.top + 10)
        cam_map = {
            "Jenifer's Bedroom": "1 J's Room",
            "Upstairs Hall": "2 Up Hall",
            "Living Room": "3 Living",
            "Dining Room": "4 Dining",
            "Bathroom": "5 Bath",
            "Kitchen": "6 Kitchen",
            "Left Hallway": "7 L Hall",
            "Right Hallway": "8 R Hall",
        }
        # draw simple 3D-ish node links
        for name, (mx, my) in CAM_POS.items():
            if name not in cam_map:
                continue
            sx = map_rect.left + 15 + int((mx - 100) * 0.28)
            sy = map_rect.top + 55 + int((my - 100) * 0.45)
            for nb in PATHS.get(name, []):
                if nb in cam_map and nb in CAM_POS:
                    nx, ny = CAM_POS[nb]
                    ex = map_rect.left + 15 + int((nx - 100) * 0.28) + 35
                    ey = map_rect.top + 55 + int((ny - 100) * 0.45) + 12
                    pygame.draw.line(self.screen, (35, 55, 40), (sx + 35, sy + 12), (ex, ey), 1)
        self.cam_buttons = {}
        for name, (mx, my) in CAM_POS.items():
            if name not in cam_map:
                continue
            sx = map_rect.left + 15 + int((mx - 100) * 0.28)
            sy = map_rect.top + 55 + int((my - 100) * 0.45)
            rect = pygame.Rect(sx, sy, 72, 24)
            self.cam_buttons[name] = rect
            selected = (self.current_cam == name)
            has_ai = (self.ai.location == name)
            has_dad = getattr(self, "dad", None) and self.dad.active and self.dad.location == name
            col = AMBER if selected else (RED if has_ai else (80, 120, 200) if has_dad else (50, 80, 55))
            pygame.draw.rect(self.screen, col, rect, 0 if selected else 1, border_radius=4)
            label = cam_map[name]
            txt = self.small_font.render(label, True, BLACK if selected else WHITE)
            self.screen.blit(txt, (sx + 4, sy + 3))
            if has_ai and has_dad and not selected:
                pygame.draw.circle(self.screen, (255, 220, 120), (sx + 66, sy + 6), 3)
        you = self.small_font.render("YOU: Liam's Room", True, AMBER)
        self.screen.blit(you, (map_rect.left + 12, map_rect.bottom - 24))

        self.draw_text("1-8 or click map: switch cams   SPACE/click bar: close", self.small_font, (170, 180, 170), panel.centerx, panel.bottom - 22, center=True)

    def draw_jumpscare(self):
        self.screen.fill((5, 0, 2))
        t = self.jumpscare_timer
        monster = (getattr(self, "night", 1) >= 8 and not getattr(self, "custom_night_mode", False))
        jitter_amp = 45 if monster else 25
        jitter_x = random.randint(-jitter_amp, jitter_amp)
        jitter_y = random.randint(-jitter_amp, jitter_amp)
        cx, cy = WIDTH // 2 + jitter_x, HEIGHT // 2 + jitter_y
        scale = (1.35 + t * 2.6) if monster else (1.2 + t * 2.0)
        if monster:
            # violent flashes and glitch blocks
            for _ in range(6):
                gx = random.randint(0, WIDTH - 120)
                gy = random.randint(0, HEIGHT - 60)
                gw = random.randint(80, 260)
                gh = random.randint(20, 120)
                gc = random.choice([(120, 0, 0), (30, 0, 10), (180, 20, 20), (0, 0, 0)])
                pygame.draw.rect(self.screen, gc, (gx, gy, gw, gh))
            if int(t * 30) % 2 == 0:
                self.screen.fill((40, 0, 0))

        # red strobe background
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        a = (70 + int(60 * abs(math.sin(t * 40)))) if monster else (45 + int(35 * abs(math.sin(t * 28))))
        pygame.draw.circle(flash, (170, 0, 30, min(220, a)) if monster else (120, 0, 20, a), (cx, cy), int((520 if monster else 430) * scale))
        self.screen.blit(flash, (0, 0))

        def S(v):
            return int(v * scale)

        # hair mass behind head
        hair_poly = [
            (cx - S(150 if monster else 120), cy - S(130)),
            (cx + S(150 if monster else 120), cy - S(130)),
            (cx + S(190 if monster else 150), cy + S(80)),
            (cx + S(110 if monster else 90), cy + S(250)),
            (cx - S(110 if monster else 90), cy + S(250)),
            (cx - S(190 if monster else 150), cy + S(80)),
        ]
        for i in range(5 if monster else 4):
            grow = i * (10 if monster else 8)
            poly = [(x + (grow if x > cx else -grow if x < cx else 0), y + (grow // 2 if y > cy else 0)) for x, y in hair_poly]
            base = (45, 5, 20) if monster else (25, 8, 18)
            pygame.draw.polygon(self.screen, (min(255, base[0] + i * 10), base[1] + i * 2, min(255, base[2] + i * 5)), poly)

        # face/head
        head_col = (150, 55, 70) if monster else (185, 145, 132)
        layers = 7 if monster else 5
        for i in range(layers, 0, -1):
            col = (70 + i * 14, 20 + i * 5, 30 + i * 5) if monster else (165 + i * 8, 130 + i * 6, 120 + i * 5)
            pygame.draw.ellipse(self.screen, col,
                                (cx - S(110) - i * 2, cy - S(120) - i * 2, S(220) + i * 4, S(250) + i * 4))
        pygame.draw.ellipse(self.screen, head_col, (cx - S(105), cy - S(115), S(210), S(235)))
        pygame.draw.ellipse(self.screen, (90, 20, 35) if monster else (120, 85, 80), (cx - S(105), cy - S(115), S(210), S(235)), 4 if monster else 3)

        # horns / extra monster features
        if monster:
            pygame.draw.polygon(self.screen, (80, 20, 30), [(cx - S(45), cy - S(100)), (cx - S(110), cy - S(220)), (cx - S(10), cy - S(130))])
            pygame.draw.polygon(self.screen, (80, 20, 30), [(cx + S(45), cy - S(100)), (cx + S(110), cy - S(220)), (cx + S(10), cy - S(130))])
            pygame.draw.polygon(self.screen, (140, 40, 50), [(cx - S(42), cy - S(102)), (cx - S(95), cy - S(205)), (cx - S(15), cy - S(128))], 3)
            pygame.draw.polygon(self.screen, (140, 40, 50), [(cx + S(42), cy - S(102)), (cx + S(95), cy - S(205)), (cx + S(15), cy - S(128))], 3)
            # cracks/veins
            for pts in [
                [(cx - S(60), cy - S(70)), (cx - S(30), cy - S(40)), (cx - S(50), cy - S(10))],
                [(cx + S(55), cy - S(60)), (cx + S(25), cy - S(30)), (cx + S(45), cy + S(5))],
                [(cx, cy - S(90)), (cx - S(10), cy - S(55)), (cx + S(5), cy - S(25))],
            ]:
                pygame.draw.lines(self.screen, (90, 10, 20), False, pts, 3)

        # bangs
        bangs = [(cx - S(110 if monster else 100), cy - S(100)), (cx + S(110 if monster else 100), cy - S(100)), (cx + S(80), cy - S(30)), (cx + S(25), cy - S(55)), (cx, cy - S(20)), (cx - S(25), cy - S(55)), (cx - S(80), cy - S(30))]
        pygame.draw.polygon(self.screen, (35, 5, 15) if monster else (30, 12, 22), bangs)

        # eyes
        eye_c = (255, 70, 10) if monster else ((255, 50, 50) if int(t * 12) % 2 == 0 else (255, 235, 235))
        eye_positions = [(-S(36), S(36))] if not monster else [(-S(40), S(40))]
        for ex in (-S(40 if monster else 34), S(40 if monster else 34)):
            ew, eh = (S(60), S(34)) if monster else (S(52), S(30))
            pygame.draw.ellipse(self.screen, (255, 220, 220), (cx + ex - ew//2, cy - S(52), ew, eh))
            pygame.draw.ellipse(self.screen, eye_c, (cx + ex - S(14), cy - S(43), S(28), S(18)))
            pygame.draw.ellipse(self.screen, (5, 0, 0), (cx + ex - S(8), cy - S(41), S(16), S(14)))
            pygame.draw.circle(self.screen, WHITE, (cx + ex - S(2), cy - S(39)), max(2, S(4 if monster else 3)))
            pygame.draw.arc(self.screen, (40, 10, 20), (cx + ex - ew//2 - S(2), cy - S(60), ew + S(4), S(38)), 0.12, 3.02, max(3, S(6)))
            if monster:
                # extra glow ring
                glow = pygame.Surface((S(80), S(50)), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (255, 40, 0, 70), (0, 0, S(80), S(50)))
                self.screen.blit(glow, (cx + ex - S(40), cy - S(60)))

        # mouth
        pygame.draw.line(self.screen, (110, 40, 45) if monster else (140, 100, 95), (cx, cy - S(20)), (cx - S(8), cy + S(2)), 4 if monster else 3)
        mouth = pygame.Rect(cx - S(60 if monster else 52), cy + S(18), S(120 if monster else 104), S(70 if monster else 54))
        pygame.draw.ellipse(self.screen, (10, 0, 0), mouth)
        pygame.draw.ellipse(self.screen, (200, 20, 30) if monster else (170, 45, 60), mouth, max(3, S(5)))
        teeth_n = 10 if monster else 6
        for i in range(teeth_n):
            tx = mouth.left + int((i + 0.5) * mouth.width / teeth_n)
            th = S(30 if monster else 18)
            tw = S(7 if monster else 6)
            pygame.draw.polygon(self.screen, (245, 245, 235), [(tx - tw, mouth.top + S(4)), (tx + tw, mouth.top + S(4)), (tx, mouth.top + th)])
            if monster and i % 2 == 0:
                pygame.draw.polygon(self.screen, (245, 245, 235), [(tx - tw, mouth.bottom - S(4)), (tx + tw, mouth.bottom - S(4)), (tx, mouth.bottom - th)])

        # neck/shoulders/claws hint
        pygame.draw.rect(self.screen, (120, 45, 55) if monster else (175, 140, 128), (cx - S(28), cy + S(100), S(56), S(48)), border_radius=S(10))
        pygame.draw.polygon(self.screen, (70, 10, 20) if monster else (70, 20, 35), [(cx - S(110), cy + S(145)), (cx + S(110), cy + S(145)), (cx + S(50), cy + S(190)), (cx - S(50), cy + S(190))])
        if monster:
            for sx, ex, yb in [(-S(120), -S(170), S(120)), (S(120), S(170), S(120))]:
                pygame.draw.line(self.screen, (90, 20, 30), (cx + sx, cy + S(110)), (cx + ex, cy + yb), 8)
                pygame.draw.circle(self.screen, (200, 200, 190), (cx + ex, cy + yb), S(6))

        if t > 0.15:
            label = "MONSTER JENIFER" if monster else "MS. JENIFER"
            col = (255, 30, 30) if monster else (255, 40, 40)
            for dx, dy in ((-2,0),(2,0),(0,-2),(0,2)):
                self.draw_text(label, self.title_font, (80,0,0), WIDTH // 2 + dx + random.randint(-4,4), HEIGHT - 110 + dy + random.randint(-3,3), center=True)
            self.draw_text(label, self.title_font, col, WIDTH // 2 + random.randint(-4,4), HEIGHT - 110 + random.randint(-3,3), center=True, shadow=True)
        self.draw_vignette(190 if monster else 160)

    def draw_gameover(self):
        self.screen.fill(BLACK)
        self.draw_text("GAME OVER", self.title_font, RED, WIDTH // 2, 260, center=True)
        self.draw_text(f"Ms. Jenifer found you in her house on Night {self.night}.", self.font, WHITE, WIDTH // 2, 340, center=True)
        self.draw_text("Press ENTER to retry night, ESC for menu", self.small_font, LIGHT_GRAY, WIDTH // 2, 420, center=True)

    def _draw_summary(self, y0=380):
        s = self.night_summary or {}
        if not s:
            return
        lines = [
            f"Power left: {s.get('power_left', 0)}%   Peak anger: {s.get('peak_anger', 0)}%",
            f"Hides: {s.get('hides', 0)}   Lectures: {s.get('lectures', 0)}   Blocks: {s.get('blocks', 0)}   Close calls survived: {s.get('survived', 0)}",
        ]
        for i, line in enumerate(lines):
            self.draw_text(line, self.small_font, (190, 200, 190), WIDTH // 2, y0 + i * 28, center=True)

    def draw_win_night(self):
        self.screen.fill(BLACK)
        self.draw_text("6:00 AM", self.title_font, GREEN, WIDTH // 2, 210, center=True)
        self.draw_text(f"You survived Night {self.night} in Jenifer's house!", self.font, WHITE, WIDTH // 2, 290, center=True)
        self._draw_summary(350)
        self.draw_text("Press ENTER/click for next night", self.small_font, LIGHT_GRAY, WIDTH // 2, 440, center=True)

    def draw_win_game(self):
        self.screen.fill(BLACK)
        self.draw_text("YOU SURVIVED", self.title_font, GREEN, WIDTH // 2, 180, center=True)
        if self.custom_night_mode:
            self.draw_text(f"CUSTOM NIGHT COMPLETE (AI {self.ai.base_level})", self.font, WHITE, WIDTH // 2, 250, center=True)
            self.draw_text("Ms. Jenifer couldn't catch you tonight.", self.small_font, LIGHT_GRAY, WIDTH // 2, 300, center=True)
        else:
            if self.night >= 8:
                title = "YOU SURVIVED THE MONSTER NIGHT"
                sub = "Bonus night complete! Jenifer returns to normal... for now."
            elif self.night >= 6:
                title = "BONUS ROUND COMPLETE!"
                sub = "Night 5 was the final story night. Bonus rounds cleared!"
            elif self.night == 5:
                title = "STORY COMPLETE: NIGHT 5 SURVIVED"
                sub = "The game ends here. Nights 6-8 are unlocked as bonus rounds!"
            else:
                title = "ALL 5 NIGHTS AT JENIFER'S HOUSE"
                sub = "Morning comes. The house is finally quiet..."
            self.draw_text(title, self.font, WHITE, WIDTH // 2, 250, center=True)
            self.draw_text(sub, self.small_font, LIGHT_GRAY, WIDTH // 2, 300, center=True)
        self._draw_summary(360)
        self.draw_text("Press ENTER/click to return to menu", self.small_font, LIGHT_GRAY, WIDTH // 2, 450, center=True)

    def draw_blackout(self):
        self.screen.fill((2, 2, 4))
        # faint room silhouette and flicker
        t = pygame.time.get_ticks() * 0.001
        flicker = 0.02 + 0.03 * (0.5 + 0.5 * math.sin(t * 3.7)) * (0.5 + 0.5 * math.sin(t * 11.0))
        if flicker > 0.03:
            glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(glow, (40, 35, 30, int(60 * flicker)), (204, 170, 616, 300))
            self.screen.blit(glow, (0, 0))
        self.draw_text("POWER OUT", self.big_font, (120, 120, 130), WIDTH // 2, HEIGHT // 2 - 20, center=True, shadow=True)
        self.draw_text("She's in the house...", self.font, (90, 80, 80), WIDTH // 2, HEIGHT // 2 + 30, center=True)
        self.draw_vignette(180)

    def draw_hiding_view(self):
        self.screen.fill((4, 4, 6))
        # view from under Liam's bed
        # bed underside/frame above
        pygame.draw.rect(self.screen, (35, 28, 22), (40, 40, WIDTH - 80, 120), border_radius=6)
        pygame.draw.rect(self.screen, (55, 44, 34), (40, 40, WIDTH - 80, 120), 3, border_radius=6)
        for i in range(10):
            x = 90 + i * 90
            pygame.draw.rect(self.screen, (28, 22, 18), (x, 150, 18, 180), border_radius=3)  # slats/supports
        # mattress bottom shadow
        pygame.draw.rect(self.screen, (25, 22, 28), (60, 120, WIDTH - 120, 60))

        # floor/carpet
        floor = pygame.Rect(60, 320, WIDTH - 120, 340)
        pygame.draw.rect(self.screen, (30, 28, 34), floor)
        for y in range(floor.top, floor.bottom, 28):
            pygame.draw.line(self.screen, (38, 35, 42), (floor.left, y), (floor.right, y), 1)
        for x in range(floor.left, floor.right, 40):
            pygame.draw.line(self.screen, (36, 33, 40), (x, floor.top), (x, floor.bottom), 1)

        # gap to room (left/right edges under bed)
        left_gap = pygame.Rect(60, 260, 120, 90)
        right_gap = pygame.Rect(WIDTH - 180, 260, 120, 90)
        pygame.draw.rect(self.screen, (12, 12, 18), left_gap)
        pygame.draw.rect(self.screen, (12, 12, 18), right_gap)
        pygame.draw.rect(self.screen, (45, 40, 38), left_gap, 2)
        pygame.draw.rect(self.screen, (45, 40, 38), right_gap, 2)

        # dust/particles
        for i in range(18):
            px = 120 + (i * 47) % (WIDTH - 240)
            py = 340 + (i * 31) % 240
            pygame.draw.circle(self.screen, (70, 70, 75), (px, py), 2)

        # danger cues from gaps
        if self.ai.location in ("Bedroom L Door", "Left Hallway"):
            pygame.draw.ellipse(self.screen, (95, 75, 45), (left_gap.left + 20, left_gap.top + 20, 70, 40))
            pygame.draw.circle(self.screen, (30, 20, 18), (left_gap.left + 45, left_gap.top + 38), 6)  # feet/shadow hint
            self.draw_text("Footsteps near the left side of the bed...", self.small_font, (170, 145, 120), WIDTH // 2, 540, center=True)
        elif self.ai.location in ("Bedroom R Door", "Right Hallway"):
            pygame.draw.ellipse(self.screen, (95, 75, 45), (right_gap.left + 30, right_gap.top + 20, 70, 40))
            pygame.draw.circle(self.screen, (30, 20, 18), (right_gap.left + 75, right_gap.top + 38), 6)
            self.draw_text("Footsteps near the right side of the bed...", self.small_font, (170, 145, 120), WIDTH // 2, 540, center=True)
        else:
            self.draw_text("Quiet under the bed... for now.", self.small_font, (130, 130, 140), WIDTH // 2, 540, center=True)

        self.draw_text("HIDING UNDER THE BED", self.big_font, (185, 185, 195), WIDTH // 2, 95, center=True, shadow=True)
        self.draw_text("Press H to crawl out", self.font, AMBER, WIDTH // 2, HEIGHT - 70, center=True)
        # anger/power/hide-time mini HUD
        anger = int(self.ai.anger)
        acol = (120, 200, 120) if anger < 35 else (220, 200, 80) if anger < 70 else (230, 80, 80)
        self.draw_text(f"Anger: {anger}%", self.small_font, acol, 40, 30)
        self.draw_text(f"Power: {int(self.power)}%", self.small_font, LIGHT_GRAY, 40, 54)
        hcol = (255, 120, 120) if self.hide_time_left <= 5 else AMBER
        self.draw_text(f"Hide time left: {int(math.ceil(self.hide_time_left))}s", self.small_font, hcol, 40, 78)
        if self.toast_timer > 0 and self.toast:
            self.draw_text(self.toast, self.small_font, WHITE, WIDTH // 2, 580, center=True, shadow=True)
        self.draw_vignette(170)

    def draw_pause(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 220, HEIGHT // 2 - 140, 440, 280)
        pygame.draw.rect(self.screen, (28, 28, 34), box, border_radius=10)
        pygame.draw.rect(self.screen, AMBER, box, 2, border_radius=10)
        self.draw_text("PAUSED", self.big_font, WHITE, box.centerx, box.top + 50, center=True, shadow=True)
        resume = pygame.Rect(box.centerx - 120, box.top + 100, 240, 38)
        restart = pygame.Rect(box.centerx - 120, box.top + 150, 240, 38)
        menu = pygame.Rect(box.centerx - 120, box.top + 200, 240, 38)
        self.ui["pause_resume"] = resume
        self.ui["pause_restart"] = restart
        self.ui["pause_menu"] = menu
        for r, label in ((resume, "Resume (P)"), (restart, "Restart Night (R)"), (menu, "Main Menu (M)")):
            pygame.draw.rect(self.screen, (40, 40, 48), r, border_radius=6)
            pygame.draw.rect(self.screen, AMBER, r, 2, border_radius=6)
            self.draw_text(label, self.small_font, WHITE, r.centerx, r.centery, center=True)
        self.draw_text("Esc: leave night prompt", self.small_font, GRAY, box.centerx, box.bottom - 22, center=True)

    def draw_cutscene_night5(self):
        t = self.cutscene_timer
        # dawn progression
        p = clamp(t / 14.0, 0.0, 1.0)
        top = (int(10 + 40 * p), int(12 + 60 * p), int(30 + 120 * p))
        bot = (int(20 + 120 * p), int(40 + 140 * p), int(60 + 120 * p))
        self.draw_vertical_gradient((0, 0, WIDTH, HEIGHT), top, bot)

        # house silhouette / room shapes
        ground_y = int(HEIGHT * 0.68)
        pygame.draw.rect(self.screen, (25, 22, 28), (0, ground_y, WIDTH, HEIGHT - ground_y))
        # window glow fading to morning
        win_col = (int(120 - 40 * p), int(110 - 20 * p), int(80 + 80 * p))
        pygame.draw.rect(self.screen, win_col, (WIDTH//2 - 140, 220, 280, 170), border_radius=8)
        pygame.draw.rect(self.screen, (60, 55, 50), (WIDTH//2 - 140, 220, 280, 170), 4, border_radius=8)
        pygame.draw.line(self.screen, (60, 55, 50), (WIDTH//2, 220), (WIDTH//2, 390), 3)
        pygame.draw.line(self.screen, (60, 55, 50), (WIDTH//2 - 140, 305), (WIDTH//2 + 140, 305), 3)

        # simple Liam under bed -> safe in morning
        if t < 5.0:
            self.draw_text("6:00 AM...", self.big_font, WHITE, WIDTH//2, 120, center=True, shadow=True)
            self.draw_text("Liam stays hidden under the bed as footsteps fade away.", self.font, (235,235,240), WIDTH//2, 470, center=True)
        elif t < 9.0:
            self.draw_text("Morning light fills Jenifer's house.", self.big_font, (255, 245, 220), WIDTH//2, 120, center=True, shadow=True)
            self.draw_text("Jenifer calms down. Liam is safe... for now.", self.font, (245,240,230), WIDTH//2, 470, center=True)
            # small calm Jenifer silhouette in window
            self.draw_jenifer_silhouette(WIDTH//2, 330, danger=False, scale=0.9)
        else:
            self.draw_text("STORY COMPLETE", self.big_font, (255, 245, 220), WIDTH//2, 120, center=True, shadow=True)
            self.draw_text("You survived 5 nights in Jenifer's house.", self.font, WHITE, WIDTH//2, 450, center=True)
            self.draw_text("Nights 6-8 are now available as bonus rounds.", self.font, AMBER, WIDTH//2, 490, center=True)

        if int(t * 2) % 2 == 0 or t > 10.0:
            self.draw_text("Press ENTER/SPACE/ESC to continue", self.small_font, (230,230,230), WIDTH//2, HEIGHT - 40, center=True)
        self.draw_vignette(80)

    def draw(self):
        self.ui = {}
        self.cam_buttons = {}
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "custom_night":
            self.draw_custom_night()
        elif self.state == "night_intro":
            self.draw_night_intro()
        elif self.state == "playing":
            if self.blackout:
                self.draw_blackout()
            elif self.hiding:
                self.draw_hiding_view()
            else:
                self.draw_office()
                if self.cam_anim > 0.01 and self.power > 0:
                    # slide camera panel
                    self.draw_camera(anim=self.cam_anim)
            if self.paused and not self.blackout:
                self.draw_pause()
        elif self.state == "cutscene_night5":
            self.draw_cutscene_night5()
        elif self.state == "jumpscare":
            self.draw_jumpscare()
        elif self.state == "gameover":
            self.draw_gameover()
        elif self.state == "win_night":
            self.draw_win_night()
        elif self.state == "win_game":
            self.draw_win_game()

        if self.confirm_quit:
            self.draw_confirm_quit()

        pygame.display.flip()

    def draw_confirm_quit(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 250, HEIGHT // 2 - 95, 500, 190)
        pygame.draw.rect(self.screen, (28, 28, 34), box, border_radius=10)
        pygame.draw.rect(self.screen, AMBER, box, 3, border_radius=10)
        if self.confirm_action == "abandon_night":
            title = "Leave this night?"
            msg = "Return to menu? Current night progress will be lost."
            yes_label = "Leave (Y)"
        else:
            title = "Quit the game?"
            msg = "Close Five Nights at Jenifer's House?"
            yes_label = "Quit (Y)"
        self.draw_text(title, self.font, WHITE, box.centerx, box.top + 42, center=True, shadow=True)
        self.draw_text(msg, self.small_font, LIGHT_GRAY, box.centerx, box.top + 78, center=True)
        yes = pygame.Rect(box.centerx - 165, box.top + 118, 140, 38)
        no = pygame.Rect(box.centerx + 25, box.top + 118, 140, 38)
        self.ui["confirm_yes"] = yes
        self.ui["confirm_no"] = no
        pygame.draw.rect(self.screen, (70, 35, 35), yes, border_radius=6)
        pygame.draw.rect(self.screen, (220, 90, 90), yes, 2, border_radius=6)
        pygame.draw.rect(self.screen, (35, 50, 35), no, border_radius=6)
        pygame.draw.rect(self.screen, (100, 190, 100), no, 2, border_radius=6)
        self.draw_text(yes_label, self.small_font, WHITE, yes.centerx, yes.centery, center=True)
        self.draw_text("Cancel (N/Esc)", self.small_font, WHITE, no.centerx, no.centery, center=True)


def main():
    try:
        game = Game()
        game.run()
    except Exception:
        # ensure pygame quits cleanly on unexpected errors and log traceback
        try:
            crash_path = os.path.join(os.path.dirname(__file__), "crash.log")
            with open(crash_path, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
