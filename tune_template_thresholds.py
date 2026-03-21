import argparse
import json
import os
from datetime import datetime
from glob import glob

import cv2
import numpy as np


def frange(start, end, step):
    values = []
    current = start
    while current <= end + 1e-9:
        values.append(round(current, 4))
        current += step
    return values


def dedupe_points(points, min_distance):
    filtered = []
    for pt in points:
        is_duplicate = False
        for existing in filtered:
            distance = ((pt[0] - existing[0]) ** 2 + (pt[1] - existing[1]) ** 2) ** 0.5
            if distance < min_distance:
                is_duplicate = True
                break
        if not is_duplicate:
            filtered.append(pt)
    filtered.sort(key=lambda p: p[1])
    return filtered


def detect_single(result, threshold, template_w, template_h):
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < threshold:
        return {
            "threshold": threshold,
            "hit_count": 0,
            "score": float(max_val),
            "centers": [],
        }

    center = (int(max_loc[0] + template_w // 2), int(max_loc[1] + template_h // 2))
    return {
        "threshold": threshold,
        "hit_count": 1,
        "score": float(max_val),
        "centers": [center],
    }


def detect_multi(result, threshold, template_w, template_h, min_distance):
    y_coords, x_coords = np.where(result >= threshold)
    points = []
    for x, y in zip(x_coords, y_coords):
        points.append((int(x + template_w // 2), int(y + template_h // 2)))

    centers = dedupe_points(points, min_distance)
    score = float(np.max(result)) if result.size > 0 else 0.0
    return {
        "threshold": threshold,
        "hit_count": len(centers),
        "score": score,
        "centers": centers,
    }


def sanitize_name(name):
    keep = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)


def draw_overlay(screen, template_w, template_h, detections, title):
    output = screen.copy()
    cv2.putText(output, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

    for idx, center in enumerate(detections):
        x1 = max(0, center[0] - template_w // 2)
        y1 = max(0, center[1] - template_h // 2)
        x2 = min(output.shape[1] - 1, x1 + template_w)
        y2 = min(output.shape[0] - 1, y1 + template_h)
        cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(output, center, 4, (0, 255, 0), -1)
        cv2.putText(output, str(idx + 1), (center[0] + 8, center[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return output


def resolve_templates(args):
    templates = []

    for item in args.template:
        if os.path.isabs(item) and os.path.exists(item):
            templates.append(item)
            continue

        if os.path.exists(item):
            templates.append(os.path.abspath(item))
            continue

        candidate = os.path.abspath(os.path.join("assets", item))
        if os.path.exists(candidate):
            templates.append(candidate)
            continue

        raise FileNotFoundError(f"Template not found: {item}")

    if args.templates_glob:
        for path in glob(args.templates_glob):
            if os.path.isfile(path):
                templates.append(os.path.abspath(path))

    unique = []
    seen = set()
    for t in templates:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def pick_suggested(evaluations):
    passed = [ev for ev in evaluations if ev["hit_count"] > 0]
    if not passed:
        return None

    # Suggest highest threshold that still detects something to reduce false positives.
    return max(passed, key=lambda ev: ev["threshold"])


def main():
    parser = argparse.ArgumentParser(
        description="Tune template-matching thresholds on a single screenshot."
    )
    parser.add_argument("--image", required=True, help="Path to screenshot image")
    parser.add_argument(
        "--template",
        action="append",
        default=[],
        help="Template path or filename under assets/. Can pass multiple times.",
    )
    parser.add_argument(
        "--templates-glob",
        default="",
        help="Optional glob for batch templates, ex: assets/*.png",
    )
    parser.add_argument("--mode", choices=["single", "multi"], default="single")
    parser.add_argument("--threshold-start", type=float, default=0.4)
    parser.add_argument("--threshold-end", type=float, default=0.9)
    parser.add_argument("--threshold-step", type=float, default=0.05)
    parser.add_argument("--min-distance", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=5, help="Print top K centers")
    parser.add_argument("--out-dir", default="debug_img")
    parser.add_argument("--output-json", default="", help="Optional report json path")

    args = parser.parse_args()

    if args.threshold_step <= 0:
        raise ValueError("--threshold-step must be > 0")
    if args.threshold_end < args.threshold_start:
        raise ValueError("--threshold-end must be >= --threshold-start")

    image_path = os.path.abspath(args.image)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    templates = resolve_templates(args)
    if not templates:
        raise ValueError("No templates provided. Use --template or --templates-glob")

    screen = cv2.imread(image_path)
    if screen is None:
        raise RuntimeError(f"Cannot read input image: {image_path}")

    os.makedirs(args.out_dir, exist_ok=True)

    thresholds = frange(args.threshold_start, args.threshold_end, args.threshold_step)
    report = {
        "image": image_path,
        "mode": args.mode,
        "thresholds": thresholds,
        "results": [],
    }

    print("=" * 80)
    print(f"Image: {image_path}")
    print(f"Mode: {args.mode}")
    print(f"Thresholds: {thresholds}")
    print("=" * 80)

    for template_path in templates:
        template = cv2.imread(template_path)
        if template is None:
            print(f"[SKIP] Cannot read template: {template_path}")
            continue

        th, tw = template.shape[:2]
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)

        evaluations = []
        for threshold in thresholds:
            if args.mode == "single":
                ev = detect_single(result, threshold, tw, th)
            else:
                ev = detect_multi(result, threshold, tw, th, args.min_distance)
            evaluations.append(ev)

        suggested = pick_suggested(evaluations)
        max_score = float(np.max(result)) if result.size > 0 else 0.0

        print(f"\nTemplate: {template_path}")
        print(f"- max_score: {max_score:.4f}")

        if suggested:
            top_centers = suggested["centers"][: args.top_k]
            print(f"- suggested_threshold: {suggested['threshold']:.2f}")
            print(f"- hit_count: {suggested['hit_count']}")
            print(f"- centers(top {args.top_k}): {top_centers}")

            overlay_title = (
                f"{os.path.basename(template_path)} | threshold={suggested['threshold']:.2f} "
                f"| hits={suggested['hit_count']}"
            )
            overlay = draw_overlay(screen, tw, th, suggested["centers"], overlay_title)
            overlay_name = (
                f"debug_threshold_{sanitize_name(os.path.basename(image_path))}"
                f"_{sanitize_name(os.path.basename(template_path))}.png"
            )
            overlay_path = os.path.join(args.out_dir, overlay_name)
            cv2.imwrite(overlay_path, overlay)
            print(f"- overlay: {overlay_path}")
        else:
            print("- suggested_threshold: None (no threshold produced a hit)")
            overlay_path = ""

        report["results"].append(
            {
                "template": template_path,
                "max_score": max_score,
                "suggested": suggested,
                "overlay": overlay_path,
                "evaluations": evaluations,
            }
        )

    output_json = args.output_json
    if not output_json:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_json = os.path.join(args.out_dir, f"threshold_report_{stamp}.json")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"Saved report: {output_json}")
    print("Done.")


if __name__ == "__main__":
    main()

