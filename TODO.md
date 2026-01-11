# SeenSlide Desktop - TODO List

## Pending Tasks

### Slide Deduplication Enhancement
**Priority:** Medium
**Status:** Planned

**Issue:**
When a presenter navigates backwards in their presentation (e.g., goes back to a previous slide upon viewer request), the current deduplication logic may treat this as a new slide and upload it again, creating duplicates.

**Current Behavior:**
- Slides are captured and uploaded in sequence
- Deduplication primarily uses perceptual hashing to detect similar slides
- Navigation backwards may bypass deduplication checks

**Required Changes:**
1. Update deduplication logic to maintain a history of all previously uploaded slides in the current session
2. When capturing a slide, check against the entire session history, not just recent slides
3. If a slide matches a previously uploaded slide (even from earlier in the presentation), skip re-uploading
4. Consider adding slide position/index tracking to handle intentional re-showing of slides

**Files to Review:**
- `modules/capture/deduplication.py` (or equivalent deduplication module)
- `modules/capture/slide_processor.py` (or slide capture logic)
- Session state management

**Implementation Notes:**
- This should preserve the ability to detect actual slide updates (e.g., presenter edits a slide and shows it again)
- Need to balance between preventing duplicates and allowing legitimate re-uploads
- Consider memory implications of maintaining full session history

**Estimated Effort:** 2-3 hours

---

## Completed Tasks
(Add completed tasks here as they're finished)
