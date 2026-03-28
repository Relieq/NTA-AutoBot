import argparse
import os

import cv2

from modules.captcha import CaptchaSolver


def draw_preview(image, solver, ok_found, ok_score, ok_loc, ok_template, title_found):
    output = image.copy()

    cv2.putText(output, f"Captcha title detected: {title_found}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    cv2.putText(output, f"btn_ok_captcha detected: {ok_found} (score={ok_score:.4f})", (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    x1, y1, x2, y2 = solver._icon_boxes()[0]
    cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(output, "Spam target: icon #1", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    if ok_found and ok_loc is not None and ok_template is not None:
        h, w = ok_template.shape[:2]
        bx1, by1 = ok_loc
        bx2, by2 = bx1 + w, by1 + h
        cv2.rectangle(output, (bx1, by1), (bx2, by2), (255, 200, 0), 2)
        cx = bx1 + w // 2
        cy = by1 + h // 2
        cv2.circle(output, (cx, cy), 6, (255, 200, 0), -1)
        cv2.putText(output, "Tap OK here", (bx1, max(20, by1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)

    return output


def main():
    parser = argparse.ArgumentParser(description="Offline captcha check for spam strategy (#1 + OK).")
    parser.add_argument("--image", required=True, help="Path to screenshot containing captcha")
    parser.add_argument("--assets-dir", default="assets", help="Assets directory")
    parser.add_argument("--save-debug", default="", help="Optional output path for annotated debug image")
    args = parser.parse_args()

    image_path = os.path.abspath(args.image)
    screen = cv2.imread(image_path)
    if screen is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    solver = CaptchaSolver(assets_dir=args.assets_dir)

    title_found = solver.detect_captcha(screen)
    ok_found, ok_score, ok_loc, ok_template = solver._find_btn_ok_captcha(screen)

    print("=" * 80)
    print(f"Image: {image_path}")
    print(f"Captcha title detected: {title_found}")
    print(f"btn_ok_captcha detected: {ok_found} (score={ok_score:.4f})")

    ix1, iy1, ix2, iy2 = solver._icon_boxes()[0]
    print(f"Spam icon #1 bbox: ({ix1}, {iy1}) -> ({ix2}, {iy2})")

    if ok_found and ok_loc is not None and ok_template is not None:
        click_x = ok_loc[0] + ok_template.shape[1] // 2
        click_y = ok_loc[1] + ok_template.shape[0] // 2
        print(f"Suggested OK click: ({click_x}, {click_y})")
    else:
        print("Suggested OK click: not found")

    if args.save_debug:
        out_path = os.path.abspath(args.save_debug)
    else:
        debug_dir = os.path.join(os.getcwd(), "debug_img")
        os.makedirs(debug_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        out_path = os.path.join(debug_dir, f"captcha_spam_preview_{base_name}.png")

    debug_img = draw_preview(screen, solver, ok_found, ok_score, ok_loc, ok_template, title_found)
    cv2.imwrite(out_path, debug_img)
    print(f"Saved debug image: {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()

