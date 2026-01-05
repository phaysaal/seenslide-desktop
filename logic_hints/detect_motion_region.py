import cv2
import numpy as np
import glob
import os

def detect_dynamic_region():
    threshold = 25
    min_area = 5000
    image_files = sorted(glob.glob(os.path.join("sample/setD", "*.png")))

    if len(image_files) < 3:
        print("Warning: needed more than 2 frames")
        if len(image_files) < 2:
            return

    print("Analyzing the files now...")

    first_frame = cv2.imread(image_files[0])
    h, w = first_frame.shape[:2]

    change_frequency = np.zeros((h, w), dtype=np.float32)

    num_pairs = len(image_files) - 1
    for i in range(num_pairs):
        frame1 = cv2.imread(image_files[i])
        frame2 = cv2.imread(image_files[i+1])

        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        diff = cv2.absdiff(gray1, gray2)

        _, pair_thresh = cv2.threshold(diff, 25, 1, cv2.THRESH_BINARY)
        cv2.add(change_frequency, pair_thresh.astype(np.float32), change_frequency)

    if num_pairs >= 2:
        min_frequency_count = max(2, int(num_pairs * 0.5))
    else:
        min_frequency_count = 1

    _, final_mask = cv2.threshold(change_frequency, min_frequency_count - 0.5, 255, cv2.THRESH_BINARY)
    final_mask = final_mask.astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    dilated = cv2.dilate(final_mask, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detected_regions = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area > min_area:
            x, y, w, h = cv2.boundingRect(contour)
            detected_regions.append((x, y, w, h))
            print(f"Detected potential video region: x={x}, y={y}, w={w}, h={h} (Area: {area})")
            
    if detected_regions:
        # Sort by area (approximation w*h)
        detected_regions.sort(key=lambda r: r[2] * r[3], reverse=True)
        best_region = detected_regions[0]
        x, y, rw, rh = best_region
        print(f"FINAL RESULT: Best candidate region: {best_region}")
        
        # Create visualization
        result_img = first_frame.copy()
        # Draw a thick green rectangle
        cv2.rectangle(result_img, (x, y), (x + rw, y + rh), (0, 255, 0), 5)
        # Add a label
        cv2.putText(result_img, "Detected Video Region", (x, y - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        
        output_path = "detection_resultD.png"
        cv2.imwrite(output_path, result_img)
        
        return best_region
    else:
        return None
    

    

if __name__ == "__main__":
    detect_dynamic_region()
