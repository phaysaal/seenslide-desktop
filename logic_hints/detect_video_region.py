
import cv2
import numpy as np
import glob
import os

def find_max_rectangle(mask):
    """
    Finds the largest rectangle of 255s in a binary mask.
    Implementation of the largest rectangle in a histogram algorithm.
    """
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int32)
    max_area = 0
    best_rect = (0, 0, 0, 0) # x, y, w, h
    
    for r in range(h):
        # Update heights of consecutive 255s ending at this row
        row = mask[r]
        heights[row == 255] += 1
        heights[row == 0] = 0
        
        # Find largest rectangle in the current histogram of heights
        stack = [] # stores (index, height)
        # Append a zero height to flush the stack at the end
        h_row = np.append(heights, 0)
        for i, height in enumerate(h_row):
            start_index = i
            while stack and stack[-1][1] >= height:
                idx, h_val = stack.pop()
                # Calculate area with h_val as the shortest bar
                area = h_val * (i - idx)
                if area > max_area:
                    max_area = area
                    best_rect = (idx, r - h_val + 1, i - idx, h_val)
                start_index = idx
            stack.append((start_index, height))
            
    return best_rect

def detect_region(image_folder="sample/setA", mode="motion", threshold=25, min_area=5000):
    """
    Detects regions based on motion.
    mode="motion": Detects high-frequency changes (videos, animations).
    mode="static": Detects stable, unchanging regions (slides, background).
    """
    # Get list of images
    image_files = sorted(glob.glob(os.path.join(image_folder, "*.png")))
    
    if len(image_files) < 3:
        print("Warning: Ideally need at least 3 frames for robust detection.")
        if len(image_files) < 2:
            return

    print(f"Analyzing {len(image_files)} images in '{mode}' mode...")

    # Read first image to get dimensions
    first_frame = cv2.imread(image_files[0])
    h, w = first_frame.shape[:2]
    
    # Initialize accumulator for change frequency
    change_frequency = np.zeros((h, w), dtype=np.float32)

    # Process consecutive pairs
    num_pairs = len(image_files) - 1
    for i in range(num_pairs):
        frame1 = cv2.imread(image_files[i])
        frame2 = cv2.imread(image_files[i+1])
        
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        
        diff = cv2.absdiff(gray1, gray2)
        
        # Binary difference for this pair
        _, pair_thresh = cv2.threshold(diff, threshold, 1, cv2.THRESH_BINARY)
        
        cv2.add(change_frequency, pair_thresh.astype(np.float32), change_frequency)

    # Mode-specific Logic
    if mode == "static":
        # We want pixels that changed very rarely. 
        # Tolerance: Allow changes in at most 10% of frames (or 1 frame if sequence is short)
        max_allowed_changes = max(1, int(num_pairs * 0.1))
        print(f"Looking for pixels that changed in {max_allowed_changes} or fewer frame pairs.")
        
        # INVERSE threshold: Values <= max_allowed_changes become 255 (White), others 0 (Black)
        _, final_mask = cv2.threshold(change_frequency, max_allowed_changes, 255, cv2.THRESH_BINARY_INV)
        
        vis_color = (255, 0, 0) # Blue for static
        label_text = "Detected Static Region"
        
    else: # mode == "motion"
        # We want pixels that changed frequently.
        min_frequency_count = max(2, int(num_pairs * 0.5)) if num_pairs >= 2 else 1
        print(f"Looking for pixels that changed in at least {min_frequency_count} out of {num_pairs} frame pairs.")
        
        _, final_mask = cv2.threshold(change_frequency, min_frequency_count - 0.5, 255, cv2.THRESH_BINARY)
        
        vis_color = (0, 255, 0) # Green for motion
        label_text = "Detected Video Region"

    if mode == "static":
        # Find the largest pure rectangle of stable pixels
        best_region = find_max_rectangle(final_mask)
        if best_region[2] * best_region[3] < min_area:
            best_region = None
    else:
        # For motion, use contour bounding boxes (as video might be irregular or scattered)
        # Apply morphological operations to merge scattered moving pixels
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        dilated = cv2.dilate(final_mask, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        detected_regions = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > min_area:
                x, y, w, h = cv2.boundingRect(contour)
                detected_regions.append((x, y, w, h))

        if detected_regions:
            detected_regions.sort(key=lambda r: r[2] * r[3], reverse=True)
            best_region = detected_regions[0]
        else:
            best_region = None

    if best_region:
        x, y, rw, rh = best_region
        print(f"FINAL RESULT: Best {mode} region: {best_region}")
        
        # Create visualization
        result_img = first_frame.copy()
        cv2.rectangle(result_img, (x, y), (x + rw, y + rh), vis_color, 5)
        cv2.putText(result_img, label_text, (x, y + 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, vis_color, 2)
        
        output_path = f"detection_result_{mode}_D.png"
        cv2.imwrite(output_path, result_img)
        print(f"Saved visualization to {output_path}")
        
        return best_region
    else:
        print(f"No significant {mode} region detected.") 
        return None

if __name__ == "__main__":
    # Test 'static' mode as requested
    detect_region(image_folder="sample/setD", mode="static")
