# Design System Inspired by Stripe

## 1. Visual Theme & Atmosphere

Stripe's website is the gold standard of fintech design — simultaneously technical and luxurious. Clean white canvas (`#ffffff`) with deep navy headings (`#061b31`) and signature purple (`#533afd`). Multi-layer blue-tinted shadows create atmospheric depth.

**Key Characteristics:**
- sohne-var with `"ss01"` — custom stylistic set
- Weight 300 as signature headline weight — light, confident
- Negative letter-spacing at display sizes (-1.4px at 56px)
- Blue-tinted multi-layer shadows: `rgba(50,50,93,0.25)`
- Deep navy (`#061b31`) headings instead of black
- Conservative border-radius (4px-8px)
- Ruby (`#ea2261`) and magenta (`#f96bee`) for gradients

## 2. Color Palette

### Primary
- Stripe Purple: `#533afd`
- Deep Navy: `#061b31`
- Pure White: `#ffffff`

### Brand Dark
- Brand Dark: `#1c1e54`
- Dark Navy: `#0d253d`

### Accent
- Ruby: `#ea2261`
- Magenta: `#f96bee`

### Interactive
- Primary: `#533afd`
- Hover: `#4434d4`
- Deep: `#2e2b8c`
- Light: `#b9b9f9`

### Neutral
- Heading: `#061b31`
- Label: `#273951`
- Body: `#64748d`
- Success: `#15be53` / text `#108c3d`

### Borders & Shadows
- Border: `#e5edf5`
- Shadow Blue: `rgba(50,50,93,0.25)`
- Shadow Black: `rgba(0,0,0,0.1)`

## 3. Typography
- Font: sohne-var, `"ss01"`
- Mono: SourceCodePro
- Weight 300 for headlines/body, 400 for UI/buttons
- Display: 56px/300/-1.4px, 48px/300/-0.96px, 32px/300/-0.64px

## 4. Components

### Buttons
- Primary: `#533afd` bg, white text, 4px radius, 8px 16px padding
- Ghost: transparent, `1px solid #b9b9f9`, 4px radius
- Neutral: transparent, `1px solid #d4dee9`, 4px radius

### Cards
- Background: `#ffffff`
- Border: `1px solid #e5edf5`
- Radius: 4-8px
- Shadow: `rgba(50,50,93,0.25) 0px 30px 45px -30px, rgba(0,0,0,0.1) 0px 18px 36px -18px`

### Badges
- Success: `rgba(21,190,83,0.2)` bg, `#108c3d` text, 4px radius
- Neutral: white bg, `1px solid #f6f9fc`, 4px radius

## 5. Layout
- 8px base grid
- Max width: ~1080px
- Conservative radius: 4px-8px
- Blue-tinted shadow system for all elevation

## 6. Depth
- Flat: no shadow
- Ambient: `rgba(23,23,23,0.06) 0px 3px 6px`
- Standard: `rgba(23,23,23,0.08) 0px 15px 35px`
- Elevated: `rgba(50,50,93,0.25) 0px 30px 45px -30px, rgba(0,0,0,0.1) 0px 18px 36px -18px`
