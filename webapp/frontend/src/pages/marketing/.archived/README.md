# Archived Business Pages

These pages are hidden from the public site as the platform is for learning and fun with stocks, not a real business.

## Archived Pages
- `Firm.jsx` - Company/firm information page
- `About.jsx` - Company about page  
- `OurTeam.jsx` - Team page
- `MissionValues.jsx` - Mission & values page

## How to Restore
If you want to restore these pages in the future:

1. Move these files back to `webapp/frontend/src/pages/marketing/`
2. Add the imports back to `webapp/frontend/src/App.jsx`:
```javascript
import Firm from "./pages/marketing/Firm";
import About from "./pages/marketing/About";
import OurTeam from "./pages/marketing/OurTeam";
import MissionValues from "./pages/marketing/MissionValues";
```

3. Add the routes back to the Routes section in `App.jsx`:
```javascript
<Route path="/firm" element={<Firm />} />
<Route path="/about" element={<About />} />
<Route path="/our-team" element={<OurTeam />} />
<Route path="/mission-values" element={<MissionValues />} />
```

The pages are fully functional and ready to use whenever you want to launch a real business in the future!
