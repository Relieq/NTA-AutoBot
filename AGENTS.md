# AGENTS Guide for NTA-AutoBot

## Big Picture
- This is an image-driven Android game bot (BlueStacks + ADB), not an API-integrated service.
- Entrypoint is `main.py`; it creates shared managers and runs an infinite priority loop.
- Task priority is fixed: `Combat` -> `DailyTask` -> `Builder`.
- Core state lives in `bot_state` (`combat_status`, cooldowns, build index, next run times).
- Most logic is optimistic and UI-verification-based (tap, then re-detect UI to confirm outcome).

## Architecture and Boundaries
- `core/device.py` (`DeviceManager`): ADB connection, `tap/swipe/precise_drag`, screenshots.
- `core/vision.py` (`VisionManager`): OpenCV template matching helpers (`find_template`, `find_all_templates`).
- `modules/scene.py`: city/map transitions (`go_to_city`, `leave_the_city`) with double-check patterns.
- `modules/daily_task.py`: simple icon flows using reusable `find_and_tap(...)` helper.
- `modules/builder.py`: OCR-heavy build/upgrade pipeline + captcha interrupt handling.
- `modules/combat.py`: map navigation, target discovery, OCR difficulty filtering, dispatch/retreat workflows.
- `modules/captcha.py`: template-driven captcha resolver (spam icon #1 + verify by `btn_ok_captcha` visibility).
- `config/build_order.py`: declarative build progression (`BUILD_SEQUENCE`) consumed by builder/main loop.

## Data and Flow Conventions (Project-Specific)
- Assets are contract inputs: every action depends on templates in `assets/` and `assets/buildings/`.
- Coordinate math assumes 1600x900 in combat (`screen_w/screen_h` in `modules/combat.py`).
- Captcha interruptions return explicit statuses: `"OK" | "INTERRUPTED" | "FATAL"` (builder/combat).
- Build progression uses idempotent checks: read current level first, skip when `current_lv >= target_lv`.
- Combat uses dead-reckoning (`camera_offset`) and explicit reset anchor (`reset_camera_to_city`).
- Difficulty filtering is blacklist-based OCR (`blacklist_difficulty`) before troop dispatch.

## Critical Workflows
- Install dependencies from `requirements.txt` (OCR stack is heavy; CPU defaults are used in code).
- Run bot loop: `python main.py`.
- Migrate map cache once when schema/cache fields change: `python migrate_map_cache.py`.
- When changing template thresholds, check `VisionManager.threshold` and per-call overrides first.
- For UI regressions, inspect artifacts in `debug_img/` (safe zone, OCR crops, checkbox rounds, retreat checks, captcha spam attempts).

## Integration Points and External Dependencies
- Emulator/device channel: `pure-python-adb` + local `adb` binary (`DeviceManager.start_adb_server`).
- Vision/OCR stack: OpenCV (`cv2`), PaddleOCR (builder/combat time), EasyOCR (combat/builder text reads).
- Captcha runtime: only template matching against `assets/title_captcha.png` and `assets/btn_ok_captcha.png`.

## Guardrails for AI Code Changes
- Keep manager boundaries intact; avoid mixing ADB calls into high-level decision logic.
- Preserve post-action verification checks (e.g., button still visible => action failed).
- Reuse existing helper patterns (`find_and_tap`, `safe_wait_and_check`) instead of adding one-off flows.
- If adding a new automated action, add corresponding asset template(s) and debug image outputs.
- Any coordinate/threshold tweak should be accompanied by a debug capture path for quick calibration.
