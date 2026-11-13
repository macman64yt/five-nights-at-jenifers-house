# Five Nights at Ms. Jenifer

A FNAF-style survival horror game built with Python and Pygame.

## Goal
Survive 5 nights as the night watch. Each night runs from **12 AM to 6 AM** (about 6 real minutes). Monitor cameras, manage power, and use doors/lights to keep **Ms. Jenifer** out of your office.

## Requirements
- Python 3.10+
- [Pygame](https://www.pygame.org/) 2.5+

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
# or
python3 -m pip install pygame
```

## Run

```bash
cd five_nights_at_ms_jenifer
python3 main.py
```

## Windows Installer
See `windows_installer/README_WINDOWS.md` for Windows install options, including:
- `windows_installer/Install.bat` (installs embedded Python + pygame and creates a shortcut)
- `windows_installer/FiveNightsAtJenifers.iss` (Inno Setup script to build a `Setup.exe` installer)

## Controls

**Menu**
- `Enter` / `Space` / `1-5` - Start night
- `Esc` - Quit

**In office**
- `Q` - Toggle left door
- `E` - Toggle right door
- `A` - Toggle left hallway light
- `D` - Toggle right hallway light
- `Space` - Open/close camera monitor
- `1-8` - Switch cameras (while monitor is open)
  - 1: Stage, 2: Hall A, 3: Hall B, 4: Classroom, 5: Closet, 6: Kitchen, 7: Left Hall, 8: Right Hall
- `Esc` - Return to menu

## Tips
- Doors, lights, and cameras all drain power. If power reaches 0%, defenses shut down.
- Use lights to check if Ms. Jenifer is at a doorway, then close the appropriate door.
- She becomes more aggressive each night. Survive all 5 nights to win.
