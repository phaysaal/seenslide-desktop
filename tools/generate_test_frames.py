#!/usr/bin/env python3
"""Generate test frames for region analyzer testing.

Creates synthetic frames that simulate:
- A static slide region (e.g., PowerPoint content)
- A dynamic video region (e.g., webcam feed)

Usage:
    python tools/generate_test_frames.py [--output-dir <dir>] [--frames <count>]
"""

import argparse
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np


def generate_test_frames(
    output_dir: Path,
    num_frames: int = 30,
    width: int = 1920,
    height: int = 1080,
    video_region: tuple = (1400, 50, 480, 360)  # x, y, w, h - top-right corner
):
    """Generate test frames with static and dynamic regions.

    Args:
        output_dir: Directory to save frames
        num_frames: Number of frames to generate
        width: Frame width
        height: Frame height
        video_region: (x, y, w, h) of the dynamic "video" region
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    vx, vy, vw, vh = video_region

    print(f"Generating {num_frames} test frames...")
    print(f"Frame size: {width}x{height}")
    print(f"Static region: (0, 0) to ({vx}, {height}) - slide content")
    print(f"Dynamic region: ({vx}, {vy}) to ({vx+vw}, {vy+vh}) - simulated webcam")

    for i in range(num_frames):
        # Create base image (dark slide background)
        img = Image.new('RGB', (width, height), (30, 30, 45))
        draw = ImageDraw.Draw(img)

        # --- STATIC REGION (Slide Content) ---
        # This content stays the same across all frames

        # Title
        draw.rectangle([50, 50, 1350, 150], fill=(40, 40, 60))
        draw.text((100, 80), "Introduction to Machine Learning", fill=(255, 255, 255))

        # Bullet points (static)
        bullets = [
            "1. Supervised Learning",
            "2. Unsupervised Learning",
            "3. Reinforcement Learning",
            "4. Neural Networks",
            "5. Deep Learning Architectures"
        ]
        y_pos = 200
        for bullet in bullets:
            draw.text((100, y_pos), bullet, fill=(200, 200, 200))
            y_pos += 60

        # Static diagram (rectangle with lines)
        draw.rectangle([100, 550, 600, 900], outline=(100, 100, 150), width=2)
        draw.line([100, 650, 600, 650], fill=(100, 100, 150), width=1)
        draw.line([100, 750, 600, 750], fill=(100, 100, 150), width=1)
        draw.text((250, 570), "Data Flow", fill=(150, 150, 180))

        # Static logo area
        draw.ellipse([700, 600, 900, 800], fill=(16, 185, 129), outline=(20, 220, 150))
        draw.text((760, 680), "Logo", fill=(255, 255, 255))

        # Slide number (static)
        draw.text((50, height - 50), "Slide 3 of 25", fill=(100, 100, 120))

        # --- DYNAMIC REGION (Webcam Simulation) ---
        # This content changes every frame

        # Video frame background
        draw.rectangle([vx, vy, vx + vw, vy + vh], fill=(20, 20, 30))

        # Simulated face (moves slightly each frame)
        face_offset_x = random.randint(-10, 10)
        face_offset_y = random.randint(-5, 5)
        face_cx = vx + vw // 2 + face_offset_x
        face_cy = vy + vh // 2 + face_offset_y

        # Face ellipse (skin tone with variation)
        skin_var = random.randint(-10, 10)
        skin_color = (200 + skin_var, 160 + skin_var, 140 + skin_var)
        draw.ellipse(
            [face_cx - 60, face_cy - 80, face_cx + 60, face_cy + 80],
            fill=skin_color
        )

        # Eyes (blink randomly)
        if random.random() > 0.1:  # 90% of time eyes are open
            draw.ellipse([face_cx - 30, face_cy - 20, face_cx - 10, face_cy], fill=(255, 255, 255))
            draw.ellipse([face_cx + 10, face_cy - 20, face_cx + 30, face_cy], fill=(255, 255, 255))
            # Pupils
            pupil_offset = random.randint(-3, 3)
            draw.ellipse([face_cx - 25 + pupil_offset, face_cy - 15, face_cx - 15 + pupil_offset, face_cy - 5], fill=(50, 50, 50))
            draw.ellipse([face_cx + 15 + pupil_offset, face_cy - 15, face_cx + 25 + pupil_offset, face_cy - 5], fill=(50, 50, 50))

        # Mouth (changes expression)
        mouth_width = random.randint(20, 40)
        draw.arc(
            [face_cx - mouth_width, face_cy + 20, face_cx + mouth_width, face_cy + 50],
            0, 180, fill=(150, 80, 80), width=3
        )

        # Background noise in video region (simulates compression artifacts)
        np_img = np.array(img)
        noise = np.random.randint(-15, 15, (vh, vw, 3), dtype=np.int16)
        np_img[vy:vy+vh, vx:vx+vw] = np.clip(
            np_img[vy:vy+vh, vx:vx+vw].astype(np.int16) + noise, 0, 255
        ).astype(np.uint8)
        img = Image.fromarray(np_img)

        # Add video label
        draw = ImageDraw.Draw(img)
        draw.rectangle([vx, vy + vh - 30, vx + vw, vy + vh], fill=(0, 0, 0, 128))
        draw.text((vx + 10, vy + vh - 25), "LIVE - Speaker View", fill=(255, 100, 100))

        # Save frame
        frame_path = output_dir / f"frame_{i:04d}.png"
        img.save(frame_path)

    print(f"\nGenerated {num_frames} frames in: {output_dir}")
    print("\nTo analyze these frames, run:")
    print(f"  python3 tools/region_analyzer.py {output_dir} --visual")


def main():
    parser = argparse.ArgumentParser(description='Generate test frames for region analyzer')
    parser.add_argument('--output-dir', '-o', default='/tmp/test_frames',
                       help='Output directory (default: /tmp/test_frames)')
    parser.add_argument('--frames', '-n', type=int, default=30,
                       help='Number of frames to generate (default: 30)')
    parser.add_argument('--width', type=int, default=1920,
                       help='Frame width (default: 1920)')
    parser.add_argument('--height', type=int, default=1080,
                       help='Frame height (default: 1080)')

    args = parser.parse_args()

    generate_test_frames(
        output_dir=Path(args.output_dir),
        num_frames=args.frames,
        width=args.width,
        height=args.height
    )


if __name__ == '__main__':
    main()
