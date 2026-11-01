LabSphere annotation coordinate update

Replace these files in your project after backing up the originals:
- teacher-dashboard/src/App.jsx
- teacher-dashboard/src/App.css
- teacher_overlay.py (project root)

This update distinguishes Chrome tab, application window, and monitor capture using the browser MediaStreamTrack displaySurface setting. Broadcast canvas dimensions follow the actual captured video dimensions. Local ink coordinates remain relative to the selected app window, while broadcast coordinates are relative to the captured source.

Important: Windows/Chromium can expose slightly different child-window bounds across versions and DPI settings. Test each share mode on the teacher PC before using it in a live lab. If a particular browser build reports inaccurate child-window bounds, use Window or Entire Screen mode and share the observed result.
