# Fusion Lower Third — First 10 Minutes Starter

If you want the absolute smallest possible thing to start building right now, follow this exactly.

## Goal of This Session
Just get a basic dark bar + two pieces of text visible in Fusion. Nothing fancy yet.

## Step-by-Step (Do These in Order)

### 1. Create a New Fusion Composition
- In Resolve, go to the Fusion page (or create a new Fusion Title generator on the timeline)
- You should see an empty node graph with a MediaOut node

### 2. Add the Background Bar (30 seconds)
- Add a **Background** node (from the toolbar or right-click → Background)
- In the Inspector:
  - Set Type to **Solid Color**
  - Color → pick a dark navy (start with RGB 6, 36, 66 or #062442)
  - Width: 1920
  - Height: 140 (we'll adjust later)
- Connect it to the MediaOut so you can see it

### 3. Move the Bar to the Bottom (30 seconds)
- Add a **Transform** node after the Background
- In the Inspector:
  - Position Y → move the bar down until it's near the bottom of the frame (around 920–960)
- Name this Transform node: `Bar_Transform`

### 4. Add Top Text (1 minute)
- Add a **Text+** node
- In the Inspector:
  - Type some placeholder text: "DAVID HART | FOUNDER"
  - Font: Arial Bold (or whatever is available)
  - Size: 40
  - Color: White
  - Alignment: Center
- Add a **Transform** node after the Text+
- Position the text inside the upper part of the dark bar
- Name the Text+ node: `TopText_TextPlus`

### 5. Add Bottom Text (1 minute)
- Add another **Text+** node
- Text: "POSITIVE AIR DUCT CLEANING MATTERS"
- Size: 52
- Color: Black
- Add a simple white rectangle behind it:
  - Add another **Background** node
  - Color: White
  - Connect it before the bottom text
- Position the white rectangle + black text in the lower part of the dark bar
- Name the bottom Text+ node: `BottomText_TextPlus`

### 6. Merge Everything Together (1–2 minutes)

You now have several separate branches. Connect them using Merge nodes:

Basic connection order (left to right):

1. Bar (Background + Bar_Transform)
2. Merge in the Top Text
3. Merge in the Bottom Text (with its white plate)

At this point you should see:
- A dark bar at the bottom
- White text on the top part of the bar
- Black text on a white strip in the bottom part of the bar

### 7. Quick Cleanup (2 minutes)

- Rename nodes using the naming guide (`FUSION_NODE_NAMING_GUIDE.md`)
- Select the main elements and create one big group called `LowerThird_Base`
- Publish two controls:
  - TopText_TextPlus.Text → publish as `Top_Text`
  - BottomText_TextPlus.Text → publish as `Bottom_Text`

### What You Should Have After 10 Minutes

- A dark bar near the bottom
- Two lines of text (one white, one black on white)
- The ability to change the text from outside the Fusion page
- A messy but working starting point

---

**This is intentionally rough.** The goal right now is just to get something visible and controllable.

Once you have this basic version on screen, take a screenshot or describe what it looks like, and we can refine positioning, sizing, and the branding plates next.

Ready when you are — go make the mess. That's the correct first step.