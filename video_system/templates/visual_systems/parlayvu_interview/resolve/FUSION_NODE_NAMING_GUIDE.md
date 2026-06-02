# Fusion Node Naming & Organization Guide

Good naming and grouping from the beginning will save a lot of pain later, especially once we add animation and multiple modes.

## Recommended Naming Convention

Use this pattern:

**Category_Description**

Examples:
- `Bar_Background`
- `Bar_Transform`
- `LeftPlate_MediaIn`
- `LeftPlate_Transform`
- `RightPlate_MediaIn`
- `RightPlate_Transform`
- `TopText_TextPlus`
- `TopText_Transform`
- `BottomText_Plate`
- `BottomText_TextPlus`
- `BottomText_Transform`
- `Main_Merge1`
- `Main_Merge2`
- `Overall_Transform`
- `OneCam_Border`
- `Animation_Driver`

### Why this works well
- Easy to find things in the node list
- Clear when you're connecting things
- Scales nicely when you add more complex animation

## Suggested Grouping Strategy

Create groups early:

1. **Bar_Group**
   Contains: Background + Transform for the main navy bar

2. **LeftPlate_Group**
   Contains: MediaIn + Transform for the left branding image

3. **RightPlate_Group**
   Contains: MediaIn + Transform for the logo

4. **TopText_Group**
   Contains: Text+ + Transform

5. **BottomText_Group**
   Contains: White plate Background + Text+ + Transform

6. **Layout_Merge**
   Final merge that combines everything above

7. **Animation_Group** (added in Phase 3)
   Will contain the nodes that drive entry/exit

8. **OneCam_Group** (added in Phase 2)
   Optional framed border logic

### How to Group
- Select the nodes
- Right-click → Group
- Give the group a clear name
- Publish important controls from inside the group to the top level

## Published Control Naming (Top Level)

When publishing controls, use clear, user-friendly names:

**Recommended Published Controls (Phase 1+2)**

- `Top_Text`
- `Bottom_Text`
- `Show_Left_Plate` (Checkbox)
- `Show_Right_Plate` (Checkbox)
- `1cam_Framed_Mode` (Checkbox)
- `1cam_Border_Thickness`
- `1cam_Border_Color`

**Later (Animation)**
- `Animation_In`
- `Animation_Out`
- `Animation_Duration_In`
- `Animation_Duration_Out`

## Pro Tips

- Name your **Merge** nodes by what they are combining (e.g., `Merge_Bar_Plates`, `Merge_Texts`, `Final_Merge`)
- Use **Transform** nodes liberally — they are cheap and make animation much easier later
- Color code nodes if it helps you (e.g., all text nodes in blue, plates in green)
- Keep your main flow roughly left-to-right or top-to-bottom

## Suggested First Pass Node List (Before Grouping)

Here's a clean starting list you can aim for in Phase 1:

1. Bar_Background
2. Bar_Transform
3. LeftPlate_MediaIn
4. LeftPlate_Transform
5. RightPlate_MediaIn
6. RightPlate_Transform
7. TopText_TextPlus
8. TopText_Transform
9. BottomPlate_Background
10. BottomText_TextPlus
11. BottomText_Transform
12. Merge_Bar_Plates
13. Merge_Texts
14. Final_Merge

Once this is working and grouped nicely, we move to Phase 2 (1cam toggle).

---

This document is meant to be printed or kept open next to Resolve while building.

Would you like me to also give you a **minimal starter Fusion composition** description (i.e., the exact nodes + connections to create first before adding text and images)? That can be the absolute smallest thing to start with.