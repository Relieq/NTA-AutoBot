import argparse
import os

import cv2

from modules.captcha import CaptchaSolver


def draw_analysis(image, analysis):
    output = image.copy()

    question = analysis.get("question_text", "")
    target_name = analysis.get("target_group_name", "")
    selected_index = analysis.get("selected_index", -1)

    cv2.putText(output, f"Question: {question}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(output, f"Target: {target_name}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    for icon in analysis.get("icons", []):
        idx = icon["index"]
        x1, y1, x2, y2 = icon["bbox"]
        sim = icon.get("similarity", -1.0)
        hybrid = icon.get("hybrid_score", -1.0)
        final_score = icon.get("final_score", hybrid)
        group_score = icon.get("group_model_score", 0.0)
        pred = icon.get("predicted_label", "")
        best_target = icon.get("best_target_label", "")
        best_non_target = icon.get("best_non_target_label", "")

        is_selected = idx == selected_index
        color = (0, 255, 0) if is_selected else (0, 165, 255)

        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            output,
            f"#{idx + 1} final={final_score:.4f} g_model={group_score:.4f} hybrid={hybrid:.4f}",
            (x1, max(20, y1 - 26)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
        )
        cv2.putText(
            output,
            f"pred={pred}",
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
        )
        cv2.putText(
            output,
            f"best_target={best_target} | best_non={best_non_target}",
            (x1, y2 + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
        )

    return output


def main():
    parser = argparse.ArgumentParser(description="Test captcha solver from a single screenshot.")
    parser.add_argument("--image", required=True, help="Path to screenshot containing captcha")
    parser.add_argument("--assets-dir", default="assets", help="Assets directory")
    parser.add_argument("--dataset-dir", default="dataset", help="Dataset directory for prototypes")
    parser.add_argument("--save-debug", default="", help="Optional output path for annotated debug image")

    args = parser.parse_args()

    image_path = os.path.abspath(args.image)
    screen = cv2.imread(image_path)
    if screen is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    solver = CaptchaSolver(assets_dir=args.assets_dir, dataset_dir=args.dataset_dir)
    analysis = solver.analyze_captcha(screen)

    print("=" * 80)
    print(f"Image: {image_path}")
    print(f"Question: {analysis.get('question_text', '')}")
    print(f"Target group: {analysis.get('target_group_name', '')}")

    if analysis.get("ok"):
        print(f"Selected icon: #{analysis['selected_index'] + 1}")
    else:
        print("Selected icon: None")

    for icon in analysis.get("icons", []):
        top3 = ", ".join(
            [f"{label}:{score:.4f}" for label, score in icon.get("target_group_scores", [])[:3]]
        )
        top2_non = ", ".join(
            [f"{label}:{score:.4f}" for label, score in icon.get("non_target_scores", [])[:2]]
        )
        print(
            f"- Icon {icon['index'] + 1}: sim={icon.get('similarity', -1.0):.4f}, "
            f"final={icon.get('final_score', icon.get('hybrid_score', -1.0)):.4f}, "
            f"g_model={icon.get('group_model_score', 0.0):.4f}, "
            f"hybrid={icon.get('hybrid_score', -1.0):.4f}, "
            f"variant={icon.get('selected_variant', 'orig')}, "
            f"pred={icon.get('predicted_label', '')}, "
            f"pred_orig={icon.get('predicted_label_orig', '')}, "
            f"pred_in_target={icon.get('pred_in_target', False)}, "
            f"best_target={icon.get('best_target_label', '')}, best_non={icon.get('best_non_target_label', '')}, "
            f"g_tgt={icon.get('target_group_sim', 0.0):.4f}, "
            f"g_other={icon.get('best_other_group_name', '')}:{icon.get('best_other_group_sim', 0.0):.4f}, "
            f"g_model_tgt={icon.get('target_group_prob_model', 0.0):.4f}, "
            f"g_model_other={icon.get('best_other_group_name_model', '')}:{icon.get('best_other_group_prob_model', 0.0):.4f}, "
            f"p_tgt={icon.get('target_prob', 0.0):.4f}, p_non={icon.get('non_target_prob', 0.0):.4f}, "
            f"pg_tgt={icon.get('target_group_prob', 0.0):.4f}, pg_other={icon.get('best_other_group_prob', 0.0):.4f}, "
            f"top3_tgt=[{top3}], top2_non=[{top2_non}]"
        )

    if args.save_debug:
        out_path = os.path.abspath(args.save_debug)
    else:
        debug_dir = os.path.join(os.getcwd(), "debug_img")
        os.makedirs(debug_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        out_path = os.path.join(debug_dir, f"captcha_test_{base_name}.png")

    debug_img = draw_analysis(screen, analysis)
    cv2.imwrite(out_path, debug_img)
    print(f"Saved debug image: {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()

