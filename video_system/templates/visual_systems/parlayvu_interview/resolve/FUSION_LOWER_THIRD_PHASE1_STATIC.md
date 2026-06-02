# Fusion Lower Third — Phase 1: Static Layout (Detailed Build Guide)

**Goal:** Build a clean, working static lower third in Fusion before adding any animation.

This is the foundation. Follow the steps in order.

## Prerequisites

- Open your new Resolve project.
- Create a new Fusion Title (or open the Fusion page on a clip).
- Have the following references open:
  - `style_parameters.json` (in this folder)
  - `FUSION_LOWER_THIRD_NODE_CHECKLIST.md`
  - Visual Spec document (for proportions)

## Recommended Node Order (Build Top-Down)

Add nodes in this sequence:

### Step 1: Background Bar

1. Add a **Background** node
   - Type: Solid Color
   - Color: `#062442` (or sample from legacy if you want exact match)
   - Width: 1920, Height: 120 (we'll adjust with Transform later)

2. Add a **Transform** node after it
   - Name it: `Bar_Transform`
   - Position Y: Move it near the bottom of the frame (around 920–950 depending on final height)
   - This will be our main bar

### Step 2: Left Branding Plate

1. Add a **MediaIn** or **Image** node
   - Load or link: `show_image_lower_third.png` (from assets)
   - Name it: `Left_Plate`

2. Add a **Transform** node
   - Name it: `Left_Plate_Transform`
   - Position it on the left side of the bar (roughly X: 100–150)
   - Scale it to fit nicely inside the bar height
   - Add a **Merge** node to combine it with the bar

### Step 3: Right Branding Plate

1. Add another **MediaIn** / **Image** node
   - Load: `logo_square.png`
   - Name it: `Right_Plate`

2. Add a **Transform** node
   - Name it: `Right_Plate_Transform`
   - Position on the far right of the bar
   - Usually needs slight trimming or scaling (reference legacy behavior)
   - Merge it on top of the previous result

### Step 4: Top Text Row (White)

1. Add a **Text+** node
   - Name: `Top_Text`
   - Text: Something like "DAVID HART | FOUNDER AND CEO, RAMAIR"
   - Font: Arial Bold
   - Size: Start around 38–42 (we'll tune)
   - Color: White (#FFFFFF)
   - Alignment: Center
   - Case: Uppercase (you can force this in the Text+ settings)

2. Add a **Transform** node after it
   - Position it in the upper portion of the bar

3. Merge it into the main comp

### Step 5: Bottom Text Row (Black on White)

1. First create the white background plate for the bottom row:
   - Add another **Background** node
   - Color: White
   - Make it slightly smaller than the main bar
   - Transform it into position under the top text

2. Add a **Text+** node
   - Name: `Bottom_Text`
   - Text: "WHY POSITIVE AIR DUCT CLEANING MATTERS"
   - Font: Arial Bold
   - Size: Start around 52–58
   - Color: Black
   - Alignment: Left (within the white plate area)

3. Merge the white plate + text together, then merge the result into the main lower third.

### Step 6: Basic Layout Cleanup

At this point you should have:
- Dark navy bar
- Left plate
- Right plate
- Top white text
- Bottom black text on white plate

Now:
- Group major sections (highly recommended)
- Use the Transform nodes to fine-tune positions until it looks close to the legacy reference
- Use the values in `style_parameters.json` as your starting point

### Step 7: Publish Controls (Early)

Even in the static phase, start publishing the important controls:

In the Fusion page, right-click on the nodes and publish:
- Top_Text.Text
- Bottom_Text.Text
- Left_Plate_Transform.Size
- Right_Plate_Transform.Size
- Bar_Transform.Position.Y (for height tuning)

This will make it much easier when we add animation later.

## Current Recommended Settings (Starting Values)

Use these as a baseline from `style_parameters.json`:

- Top row size: ~40 pt
- Bottom row size: ~56 pt
- Main bar color: #062442
- Top text color: #FFFFFF
- Bottom text color: #000000
- Bottom plate color: #FFFFFF

Adjust as needed while looking at real footage.

## Checklist for Phase 1 Completion

- [ ] Dark navy bar is in place and positioned correctly
- [ ] Left and right branding plates are visible and sized well
- [ ] Top text is white, bold, uppercase, and centered in the upper bar area
- [ ] Bottom text is black, bold, uppercase on a clean white plate
- [ ] Text is readable and not fighting the branding plates
- [ ] Basic controls are published
- [ ] You can change the text and see the result instantly

## Once Phase 1 is Solid

Do **not** rush into animation.

Next we will:
1. Add the 1cam Framed Mode toggle
2. Then add the first animation (entry)

---

**When you're ready to start building**, open Resolve, create a new Fusion composition, and begin at Step 1.

Let me know when you have the basic static version roughed in (even if it's ugly), and we can refine positioning together or move to the 1cam toggle.

Would you like me to also give you a suggested **node naming convention** and group structure before you start? Or shall we jump straight in?