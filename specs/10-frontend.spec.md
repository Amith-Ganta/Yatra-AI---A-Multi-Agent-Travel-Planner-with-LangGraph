# Frontend Specification — Next.js 14 Flipkart-Style UI

## Overview

Production-grade Next.js 14 application with Flipkart/Amazon design pattern. Real-time SSE trip planning with live agent progress, interactive results, and HITL approval flow.

---

## Design System

### Colors
- **Primary**: #2874F0 (Flipkart blue)
- **Secondary**: #FB641B (Flipkart orange) — CTAs only
- **Success**: #31a24c
- **Error**: #d32f2f
- **Neutral**: #f0f0f0, #666, #333

### Typography
- **Font Family**: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto"
- **Large Header**: 32px bold
- **Subheading**: 20px medium
- **Body**: 14px regular
- **Small**: 12px regular

### Spacing
Tailwind defaults (4px base unit): 1=4px, 2=8px, 4=16px, 6=24px, 8=32px

---

## Project Structure

```
frontend/
  ├── package.json
  ├── package-lock.json
  ├── next.config.js
  ├── tsconfig.json
  ├── tailwind.config.ts
  ├── postcss.config.js
  ├── .eslintrc.json
  ├── .gitignore
  ├── public/
  │   └── logo.svg
  └── src/
      ├── app/
      │   ├── layout.tsx
      │   ├── page.tsx (Home)
      │   ├── globals.css
      │   ├── plan/
      │   │   └── page.tsx (Planning form)
      │   ├── results/
      │   │   └── [threadId]/
      │   │       └── page.tsx (Results display)
      │   └── approve/
      │       └── [threadId]/
      │           └── page.tsx (HITL approval)
      ├── components/
      │   ├── Header.tsx
      │   ├── SearchBar.tsx
      │   ├── CategoryStrip.tsx
      │   ├── DealBanner.tsx
      │   ├── TripCard.tsx
      │   ├── FlightCard.tsx
      │   ├── HotelCard.tsx
      │   ├── WeatherPanel.tsx
      │   ├── BudgetBreakdown.tsx
      │   ├── ProgressBar.tsx
      │   ├── LoadingSkeleton.tsx
      │   ├── Toast.tsx
      │   └── Footer.tsx
      ├── lib/
      │   ├── api.ts (API client)
      │   ├── sse.ts (SSE stream handler)
      │   └── types.ts (TypeScript types)
      └── hooks/
          ├── useTripPlanner.ts (Main planning hook)
          └── useSSEStream.ts (SSE stream hook)
```

---

## Pages

### Home Page (src/app/page.tsx)

**Hero Section:**
- Large search bar centered (destination + date inputs)
- "Start Planning" CTA button (orange)

**Category Strip:**
- Flights | Hotels | Weather | Budget | Packages
- On click → navigate to /plan with pre-filled category

**Deal Banners:**
- Gradient cards (Flipkart "Big Billion Days" style)
- 3-5 featured destinations with prices
- Card layout: image + "From $XXX" price tag

**Footer:**
- Links to about, contact, terms
- Copyright

---

### Planning Page (/plan)

**Multi-Step Form:**
1. **Step 1 - Destination & Duration**
   - Input: Destination (autocomplete)
   - Inputs: Departure date + Return date
   - Button: Next

2. **Step 2 - Travelers & Budget**
   - Input: Party size (1-10 slider)
   - Input: Total budget ($)
   - Toggle: Include flights? hotels? weather?
   - Button: Start Planning

**Progress Bar:**
- Visual indicator: Step 1/2 → Step 2/2

**Submit:**
- POST /api/plan with state
- Navigate to /results/[threadId]
- Show SSE event stream live

---

### Results Page (/results/[threadId])

**Layout:** 
- Left (60%): SSE progress stream
- Right (40%): Collapsible results panel

**SSE Progress Stream:**
- Real-time agent progress events
- Format: "🚀 Searching flights... (32%)"
- Color changes: yellow (in-progress) → green (done)
- Duration: Shows total time taken

**Results Panel (After SSE complete):**
- Tabbed: Flights | Hotels | Weather | Budget | Itinerary

**Flight Results:**
- Card per flight: airline logo, times, price, duration
- "Select" button on best option
- Sorting: Price, Duration, Rating

**Hotel Results:**
- Card per hotel: image, rating (★★★★), price/night, neighborhood
- "View Details" button

**Weather:**
- 7-day forecast cards
- Icon + temp + condition
- "Packing advice" callout

**Budget Breakdown:**
- Pie chart or horizontal bar chart
- Categories: Flights, Hotels, Food, Activities, Misc
- Total: $X / Budget $Y

**Itinerary:**
- Card per day with activities list
- Time-based layout if available

**Bottom:**
- "Review & Approve" button (orange, floats sticky)
- Navigates to /approve/[threadId]

---

### Approval Page (/approve/[threadId])

**Layout:**
- Left (50%): Itinerary summary (read-only)
- Right (50%): Approval form

**Itinerary Summary:**
- Condensed day-by-day view
- Flights + Hotels highlighted
- Total cost reminder

**Approval Form:**
- Text area: "Any feedback or changes?"
- Toggle: "I approve this plan"
- CTA: "Submit Approval" (orange, disabled until toggle on)
- CTA: "Request Changes" (secondary)

**Success State:**
- Confirmation message: "Plan approved! Share link: [copy button]"
- Countdown to redirect to home (5s)

---

## Components

### Header
- Sticky top
- Left: Yatra AI logo (SVG)
- Center: Search bar (mini, just destination)
- Right: Account icon, notifications, cart (decorative)
- Mobile: Hamburger menu

### SearchBar
- Large input: "Where do you want to go?"
- Autocomplete list (Paris, London, Tokyo, etc.)
- Datepickers for dates below
- "Search" button (orange)

### CategoryStrip
- Horizontal scrollable on mobile
- 5 cards: Flights, Hotels, Weather, Budget, Packages
- Each: Icon + label
- On click: Filter results or navigate

### DealBanner
- Gradient background (Flipkart style)
- Image on left
- Text on right: destination name + "From $XXX"
- "Explore" CTA button
- Mobile: Stacked, image on top

### TripCard
- Used for featured destinations
- Image, title, price range, rating
- Hover: Slight lift shadow
- Click: Navigate to /plan?destination=...

### FlightCard
- Airline logo (small)
- Departure time → Arrival time
- Duration below
- Price (large, orange)
- "Select" button
- Stops info if multi-stop

### HotelCard
- Image thumbnail
- Title, rating (stars), review count
- Location/neighborhood
- Price per night (bold)
- "View Details" button
- Amenities: WiFi, Pool, etc. (icons)

### WeatherPanel
- 7 forecast days
- Each: Date, icon, temp max/min, condition
- Packing advice callout below

### BudgetBreakdown
- Pie chart using Chart.js or Recharts
- Or horizontal stacked bar
- Categories with colors
- Legend with percentages
- Total at top

### ProgressBar
- Horizontal bar
- Steps filled: green
- Current step: orange
- Label: "Step 1 of 3"

### LoadingSkeleton
- Pulsing gray bars
- Used while SSE events stream
- Matches card height/width

### Toast
- Bottom-right corner
- Auto-dismiss after 3s
- Success (green), Error (red), Info (blue)
- Close button (×)

### Footer
- Links, copyright, social (optional)

---

## API Integration

### Endpoints

**POST /api/plan**
- Body: `{ destination, departure_date, return_date, party_size, budget, selected_agents }`
- Response: `{ thread_id, message }`
- SSE stream follows: `/api/plan/stream?thread_id=...`

**GET /api/threads/{threadId}**
- Response: `{ thread_id, user_id, metadata, messages, created_at, status }`

**GET /api/plan/stream?thread_id=...**
- SSE stream: `event: progress\ndata: {...}\n\n`
- Event data: `{ agent: "flight", status: "in_progress", progress: 45 }`

**PUT /api/threads/{threadId}/approve**
- Body: `{ feedback, approved }`
- Response: `{ thread_id, status, share_url }`

---

## SSE Event Spec

Stream emits events with format:

```
event: progress
data: {
  "agent": "flight",
  "status": "in_progress",
  "message": "Searching flights from NYC to Paris...",
  "progress": 25,
  "timestamp": "2026-10-29T10:30:00Z"
}

event: complete
data: {
  "thread_id": "abc-123",
  "total_time": 8.5,
  "agents_completed": 5
}
```

---

## Environment

**.env.local:**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_STRIPE_KEY=pk_...  (optional)
```

In development: API rewrites to FastAPI via next.config.js
In production: Deployed to Vercel/Netlify, API via NEXT_PUBLIC_API_URL

---

## Build & Deploy

**Local dev:**
```bash
npm install
npm run dev
# Runs on http://localhost:3000
```

**Build:**
```bash
npm run build
# Must succeed with ZERO errors
```

**Production:**
```bash
npm run start
```

---

## Performance Targets

- **Lighthouse:** 90+ (mobile), 95+ (desktop)
- **Core Web Vitals:** LCP < 2.5s, FID < 100ms, CLS < 0.1
- **Bundle:** < 200KB (main.js)
- **SSE latency:** < 100ms per event

---

## Mobile Responsive

- **Breakpoints:** sm:640px, md:768px, lg:1024px, xl:1280px
- **Home:** Hero full width, cards stack on mobile
- **Plan:** Form fields stack on sm
- **Results:** Tabs horizontal on md+, stacked on sm
- **Approval:** Side-by-side on md+, stacked on sm

---

## Accessibility

- ARIA labels on buttons
- Semantic HTML (nav, header, main, footer)
- Color contrast: WCAG AA minimum
- Keyboard navigation: Tab through all interactive elements
- Reduced motion: Respect prefers-reduced-motion

---

## Testing

- Unit tests for hooks (useTripPlanner, useSSEStream)
- E2E tests: Playwright for full flows
- Snapshots for components

```bash
npm run test
npm run test:e2e
```

---

## Known Limitations & Future Work

- Flight search uses mock data (no real AviationStack API)
- Hotel search limited to Tavily results (no images)
- Weather forecast limited to Open-Meteo (free tier)
- No payment integration yet
- No user authentication yet
- No itinerary sharing/export
