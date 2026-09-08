# Machine type photographs

Drop real photographs here, one folder per machine type. They appear
automatically on the Machinery Rental page — no code change needed.

    frontend/public/machinery/tractor/01-front.jpg
    frontend/public/machinery/tractor/02-side.jpg
    frontend/public/machinery/rotavator/01.jpg
    ...

Rules:

* Any `.jpg`, `.jpeg`, `.png`, `.webp` or `.avif` file is picked up.
* Files are shown in filename order, so prefix with `01-`, `02-` to control
  which photo is the cover image (the first one is used on the browse grid).
* Folder names must match the machine keys exactly. The 15 valid keys are the
  folder names already created here.
* A type with no photos falls back to the built-in SVG drawing, so an empty
  folder is safe — it never shows a broken image.

Check what is still missing at any time:

    GET /api/machinery/photo-coverage

No photographs are bundled with this project. Agricultural stock imagery is
almost always licensed, so shipping third-party photos inside a farmer-facing
app would be a copyright problem rather than a shortcut.
