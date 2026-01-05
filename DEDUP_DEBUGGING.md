# Deduplication Debugging Guide

## Overview

The deduplication engine now includes comprehensive logging and screenshot saving for debugging purposes. This helps you understand exactly why screenshots are being kept or rejected.

---

## 🔍 What Gets Logged

### **Every Screen Capture:**
```
================================================================================
📸 SCREEN CAPTURE #5
  Capture ID: abc-123-def-456
  Timestamp: 2026-01-05 14:30:45.123
  Image size: 1920x1200
  Monitor: 1
  Crop region: x=480, y=300, w=960, h=600
  Crop area: 50.0% of full image

  Comparing with previous capture: xyz-789-abc-012
  Strategy: perceptual

  🔍 Perceptual Hash Comparison:
     Original image size: (1920, 1200)
     Cropped to: (960, 600) (region: x=480, y=300, w=960, h=600)
     Computing perceptual hashes (hash_size=8x8)...
     Current hash:  1a2b3c4d5e6f7a8b
     Previous hash: 1a2b3c4d5e6f7a8c
     Hamming distance: 1 (out of 64 bits)
     Similarity score: 0.984375 (1.0 = identical, 0.0 = completely different)
     Threshold: 0.95
     ✅ Images ARE similar (similarity 0.984375 >= threshold 0.95)
     Processing time: 12.45ms

  Similarity score: 0.9844
  Decision: DUPLICATE ❌
  Reason: Similarity 0.9844 >= threshold (too similar to previous)
  💾 Saved rejected screenshot: /tmp/seenslide/rejected/{session_id}/rejected_20260105_143045_123_abc123_sim0.9844.png
  💾 Saved cropped region: /tmp/seenslide/rejected/{session_id}/rejected_CROP_20260105_143045_123_abc123_sim0.9844.png
  📊 Stats: 3 unique, 2 duplicates, 40.0% rejection rate
================================================================================
```

---

## 📁 Rejected Screenshots Location

All rejected (duplicate) screenshots are saved to:
```
/tmp/seenslide/rejected/{session_id}/
```

### **File Naming Convention:**

#### Full Screenshots:
```
rejected_{timestamp}_{capture_id}_{similarity}.png
```
Example:
```
rejected_20260105_143045_123_abc12345_sim0.9844.png
```

#### Cropped Regions (when using crop_region):
```
rejected_CROP_{timestamp}_{capture_id}_{similarity}.png
```
Example:
```
rejected_CROP_20260105_143045_123_abc12345_sim0.9844.png
```

### **Filename Components:**
- `timestamp`: `YYYYMMDD_HHMMSS_fff` (millisecond precision)
- `capture_id`: First 8 characters of UUID
- `similarity`: Similarity score (0.0000 to 1.0000)

---

## 📊 Deduplication Strategies

### **1. Hash Strategy (Pixel-Perfect)**

Logs example:
```
🔍 Hash Comparison (MD5):
   Original image size: (1920, 1200)
   No cropping (comparing full images)
   Computing MD5 hashes...
   Current hash:  a1b2c3d4e5f6g7h8...9i0j1k2l3m4n5o6p
   Previous hash: a1b2c3d4e5f6g7h8...9i0j1k2l3m4n5o6q
   ❌ Hashes DIFFER (images have at least one pixel difference)
   Processing time: 8.23ms
```

**How it works:**
- Computes cryptographic hash (MD5/SHA256) of image bytes
- **Match:** Pixel-perfect identical images
- **No match:** Even 1 pixel difference = unique

---

### **2. Perceptual Strategy (Visual Similarity)**

Logs example:
```
🔍 Perceptual Hash Comparison:
   Original image size: (1920, 1200)
   Cropped to: (960, 600) (region: x=480, y=300, w=960, h=600)
   Computing perceptual hashes (hash_size=8x8)...
   Current hash:  1a2b3c4d5e6f7a8b
   Previous hash: 1a2b3c4d5e6f7a8c
   Hamming distance: 1 (out of 64 bits)
   Similarity score: 0.984375
   Threshold: 0.95
   ✅ Images ARE similar (0.984375 >= 0.95)
   Processing time: 12.45ms
```

**How it works:**
- Computes perceptual hash (pHash) - resistant to minor changes
- Calculates hamming distance between hashes
- Converts to similarity score (0.0-1.0)
- **Duplicate if:** similarity >= threshold (default 0.95)

**Good for:**
- Ignoring cursor movement
- Ignoring minor UI animations
- Slides with small changes

---

### **3. Hybrid Strategy (Multi-Stage)**

Logs example:
```
🔍 Hybrid Multi-Stage Comparison:
   Stages to check: hash → perceptual

   Stage 1/2: HASH
     🔍 Hash Comparison (MD5):
        ...hash details...
        ❌ Hashes DIFFER
     ❌ No match on stage 'hash' - Continuing to next stage

   Stage 2/2: PERCEPTUAL
     🔍 Perceptual Hash Comparison:
        ...perceptual details...
        ✅ Images ARE similar
     ✅ MATCH on stage 'perceptual' - Perceptually similar

   Final result: DUPLICATE (matched at stage 'perceptual')
   Total processing time: 18.67ms
   Match statistics: hash=2, perceptual=5, unique=3
```

**How it works:**
1. **First:** Try hash comparison (fast, exact)
2. **If no match:** Try perceptual (slower, tolerant)
3. **Result:** Duplicate if ANY stage matches

**Best of both worlds:**
- Fast exact matching when possible
- Tolerant matching as fallback

---

## 🛠️ How to Use This for Debugging

### **Step 1: Enable Logging**

Set logging level to INFO in your config or environment:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Or in config.yaml:
```yaml
logging:
  level: INFO
```

### **Step 2: Run Your Capture Session**

Start the app and capture some slides. The logs will show in the terminal.

### **Step 3: Check Rejected Folder**

After your session, review rejected screenshots:

```bash
cd /tmp/seenslide/rejected/{your-session-id}/
ls -lh
```

You'll see all rejected screenshots with their similarity scores in the filename.

### **Step 4: Visual Inspection**

Open rejected screenshots side-by-side with kept slides to understand decisions:

```bash
# View all rejected with similarity >= 0.98
find /tmp/seenslide/rejected/ -name "*sim0.98*.png" -o -name "*sim0.99*.png"

# Or use image viewer
eog /tmp/seenslide/rejected/{session-id}/*.png
```

### **Step 5: Adjust Threshold if Needed**

If you see false positives (unique slides marked as duplicates):
- **Lower the threshold** (e.g., 0.95 → 0.90)
- More slides will be kept

If you see false negatives (duplicates not caught):
- **Raise the threshold** (e.g., 0.95 → 0.98)
- More aggressive deduplication

In GUI (Direct Talk Window):
- Adjust "Deduplication Tolerance" slider
- Lower slider = stricter (keeps more)
- Higher slider = looser (rejects more)

---

## 📈 Understanding Similarity Scores

### **Score Ranges:**

| Score Range | Meaning | Typical Cause |
|------------|---------|---------------|
| **1.0000** | Pixel-perfect identical | Exact same screenshot |
| **0.99 - 0.999** | Nearly identical | Minor cursor movement, small UI change |
| **0.95 - 0.98** | Very similar | Same slide with small animation |
| **0.90 - 0.94** | Similar | Same slide layout, different content |
| **0.80 - 0.89** | Somewhat similar | Related slides, same template |
| **< 0.80** | Different | Different slides |

### **Default Threshold: 0.95**
- **Above 0.95:** Marked as DUPLICATE ❌
- **Below 0.95:** Marked as UNIQUE ✅

---

## 🐛 Common Issues and Solutions

### **Issue 1: Too Many False Duplicates**

**Symptom:** Unique slides being rejected as duplicates

**Solution:**
1. Check rejected folder and compare with kept slides
2. Look at similarity scores in logs
3. Lower threshold (e.g., 0.95 → 0.90 or 0.85)
4. Consider using crop_region to focus on slide content

---

### **Issue 2: Duplicates Not Being Caught**

**Symptom:** Same slide captured multiple times

**Solution:**
1. Check logs for similarity scores
2. Raise threshold (e.g., 0.95 → 0.97 or 0.98)
3. Switch from hash to perceptual strategy
4. Use hybrid strategy for best results

---

### **Issue 3: Too Many Screenshots in Rejected Folder**

**Symptom:** Hundreds of rejected screenshots

**Solution:**
1. This is normal! High rejection rate = good deduplication
2. Review a sample to ensure they're actually duplicates
3. If they're unique, adjust threshold down

---

### **Issue 4: Crop Region Not Working**

**Symptom:** Duplicates because of changes outside slide area

**Solution:**
1. Verify crop region in logs: `Crop region: x=..., y=..., w=..., h=...`
2. Check cropped region percentage: `Crop area: XX.X% of full image`
3. Adjust crop region to focus on presentation area only
4. Compare full vs cropped rejected images

---

## 🧹 Cleanup

The rejected folder is temporary for debugging:

```bash
# Remove all rejected screenshots
rm -rf /tmp/seenslide/rejected/

# Remove for specific session
rm -rf /tmp/seenslide/rejected/{session-id}/

# Remove old rejected screenshots (older than 7 days)
find /tmp/seenslide/rejected/ -name "*.png" -mtime +7 -delete
```

**Note:** This folder is in /tmp and will be cleared on system reboot on most Linux systems.

---

## 📝 Example Workflow

### **Debugging a Problematic Session:**

1. **Enable INFO logging**
   ```bash
   export LOG_LEVEL=INFO
   ```

2. **Start capture**
   ```bash
   python gui/main.py
   ```

3. **After session, check stats in logs:**
   ```
   📊 Stats: 25 unique, 175 duplicates, 87.5% rejection rate
   ```

4. **Review rejected folder:**
   ```bash
   cd /tmp/seenslide/rejected/{session-id}/
   ls -lh | wc -l  # Count rejected
   ```

5. **Check similarity distribution:**
   ```bash
   ls -1 | grep -oP 'sim\K[0-9.]+' | sort -n | uniq -c
   ```

6. **Visual inspection of borderline cases:**
   ```bash
   # View all rejected with similarity 0.94-0.96
   find . -name "*sim0.94*.png" -o -name "*sim0.95*.png" -o -name "*sim0.96*.png"
   ```

7. **Adjust threshold based on findings**

8. **Re-test with new threshold**

9. **Clean up when satisfied:**
   ```bash
   rm -rf /tmp/seenslide/rejected/{session-id}/
   ```

---

## 🚀 Advanced Tips

### **Compare Rejected with Kept:**

```bash
# Find the kept slides
KEPT_DIR="/tmp/seenslide/images/{session-id}/"

# Find rejected with high similarity
REJECTED_DIR="/tmp/seenslide/rejected/{session-id}/"

# Visual comparison
for f in ${REJECTED_DIR}/rejected_*sim0.9[5-9]*.png; do
    echo "Rejected: $f"
    # Find corresponding kept slide by timestamp
done
```

### **Extract Similarity Scores for Analysis:**

```bash
cd /tmp/seenslide/rejected/{session-id}/
ls -1 | grep -oP 'sim\K[0-9.]+' > scores.txt
python3 << EOF
import numpy as np
scores = np.loadtxt('scores.txt')
print(f"Mean: {scores.mean():.4f}")
print(f"Median: {np.median(scores):.4f}")
print(f"Min: {scores.min():.4f}")
print(f"Max: {scores.max():.4f}")
print(f"Std: {scores.std():.4f}")
EOF
```

### **Automated Threshold Tuning:**

Based on rejected similarity distribution, find optimal threshold:
- **Conservative:** median + 1 std dev
- **Balanced:** median + 0.5 std dev
- **Aggressive:** median

---

## 🎯 Summary

**Key Features:**
- ✅ Comprehensive logging of every capture and decision
- ✅ Rejected screenshots saved for inspection
- ✅ Detailed strategy-specific computation logs
- ✅ Crop region support with visual feedback
- ✅ Real-time statistics tracking

**Use Cases:**
- Debug why slides are being rejected/kept
- Tune deduplication threshold
- Verify crop region is working correctly
- Understand strategy behavior
- Quality assurance for presentations

**Best Practices:**
- Review rejected folder after first session
- Adjust threshold based on your use case
- Use crop_region to focus on slide content
- Clean up rejected folder periodically
- Monitor rejection rate (80-90% is normal for slide capture)

---

## 📞 Need Help?

If deduplication isn't working as expected:
1. Check logs for similarity scores
2. Review rejected screenshots
3. Adjust threshold incrementally
4. Try different strategies (hash, perceptual, hybrid)
5. Use crop_region to isolate slide content

The detailed logs will show you exactly why each decision was made!
