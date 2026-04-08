# PyMOL Visualization Workflows

## Overview

Common visualization workflows for molecular structures. Each workflow provides complete code that can be sent to PyMOL via claudemol.

## Basic Protein Visualization

### Simple Cartoon View

```python
# Load and display protein as cartoon
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.orient()
```

### Cartoon with Chain Coloring

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.util.cbc()  # Color by chain
cmd.orient()
```

### Rainbow Coloring (N to C)

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.spectrum('count', 'rainbow', 'all')
cmd.orient()
```

## Surface Visualizations

### Opaque Surface

```python
cmd.fetch('1ubq')
cmd.show('surface', 'all')
cmd.color('white', 'all')
cmd.orient()
```

### Transparent Surface with Cartoon

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.show('surface', 'all')
cmd.set('transparency', 0.7, 'all')
cmd.color('gray80', 'all')
cmd.spectrum('count', 'rainbow', 'all')
cmd.orient()
```

### Electrostatic-style Surface

```python
cmd.fetch('1ubq')
cmd.show('surface', 'all')
# Color by B-factor as proxy for flexibility
cmd.spectrum('b', 'blue_white_red', 'all')
cmd.orient()
```

## Protein-Ligand Complexes

### Basic Ligand Binding

```python
cmd.fetch('6lu7')  # SARS-CoV-2 main protease with inhibitor
cmd.show('cartoon', 'polymer.protein')
cmd.hide('lines', 'all')
cmd.show('sticks', 'organic')
cmd.color('cyan', 'polymer.protein')
cmd.color('yellow', 'organic')
cmd.util.cnc('organic')  # Color by element
cmd.hide('everything', 'solvent')
cmd.zoom('organic', buffer=8)
```

### Binding Site Visualization

```python
cmd.fetch('6lu7')

# Show protein as cartoon
cmd.show('cartoon', 'polymer.protein')
cmd.hide('lines', 'all')
cmd.color('palegreen', 'polymer.protein')

# Show ligand as sticks
cmd.show('sticks', 'organic')
cmd.util.cnc('organic')

# Highlight binding site residues
cmd.select('binding_site', 'byres organic around 5')
cmd.show('sticks', 'binding_site')
cmd.color('salmon', 'binding_site and elem C')

# Add surface to binding pocket
cmd.show('surface', 'binding_site')
cmd.set('transparency', 0.5, 'binding_site')

# Hide water
cmd.hide('everything', 'solvent')

# Focus on binding site
cmd.zoom('organic', buffer=10)
```

### Protein-Ligand with Interactions

```python
cmd.fetch('6lu7')

# Setup representations
cmd.show('cartoon', 'polymer.protein')
cmd.hide('lines', 'all')
cmd.show('sticks', 'organic')
cmd.util.cnc('organic')
cmd.hide('everything', 'solvent')

# Binding site
cmd.select('bs', 'byres organic around 4')
cmd.show('lines', 'bs')

# Show polar contacts (hydrogen bonds)
cmd.distance('hbonds', 'organic', 'bs', mode=2)
cmd.set('dash_color', 'yellow', 'hbonds')
cmd.set('dash_gap', 0.3)
cmd.set('dash_width', 2)

cmd.zoom('organic', buffer=8)
```

## Domain Highlighting

### Highlight Specific Domain

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')

# Define domain
cmd.select('domain1', 'resi 1-35')
cmd.select('domain2', 'resi 36-76')

# Color domains
cmd.color('marine', 'domain1')
cmd.color('salmon', 'domain2')

cmd.orient()
```

### Multiple Domains with Labels

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')

# Define and color domains
cmd.select('beta_sheet', 'ss s')  # Beta sheets
cmd.select('alpha_helix', 'ss h')  # Alpha helices
cmd.select('loops', 'ss l+""')  # Loops

cmd.color('blue', 'beta_sheet')
cmd.color('red', 'alpha_helix')
cmd.color('gray', 'loops')

cmd.orient()
```

## Active Site Focus

### Catalytic Residue Highlighting

```python
cmd.fetch('1trz')  # Trypsin
cmd.show('cartoon', 'polymer.protein')
cmd.hide('lines', 'all')
cmd.color('gray80', 'polymer.protein')

# Catalytic triad
cmd.select('catalytic', 'resi 57+102+195 and chain A')
cmd.show('sticks', 'catalytic')
cmd.color('yellow', 'catalytic and elem C')
cmd.util.cnc('catalytic')

cmd.zoom('catalytic', buffer=12)
```

### Mutation Site Visualization

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.color('palegreen', 'all')

# Highlight mutation site
cmd.select('mutation', 'resi 48')
cmd.show('sticks', 'mutation')
cmd.color('magenta', 'mutation and elem C')
cmd.util.cnc('mutation')

# Show nearby residues
cmd.select('nearby', 'byres mutation around 4 and not mutation')
cmd.show('lines', 'nearby')
cmd.color('gray50', 'nearby')

cmd.zoom('mutation', buffer=8)
```

## Multi-structure Comparisons

### Superposition of Two Structures

```python
cmd.fetch('1ubq', 'human')
cmd.fetch('1ubi', 'yeast')

cmd.align('yeast', 'human')

cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.color('marine', 'human')
cmd.color('salmon', 'yeast')

cmd.orient()
```

### Structure Comparison with RMSD

```python
cmd.fetch('1ubq', 'struct1')
cmd.fetch('1ubi', 'struct2')

# Align and get RMSD
cmd.align('struct2', 'struct1')

cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')

# Color by RMSD deviation
cmd.color('blue', 'struct1')
cmd.spectrum('pc', 'blue_white_red', 'struct2')

cmd.orient()
```

## Publication-Quality Figures

### Standard White Background

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.util.cbc()
cmd.orient()

# Publication settings
cmd.bg_color('white')
cmd.set('ray_trace_mode', 1)
cmd.set('ray_shadows', 'off')
cmd.set('antialias', 2)
cmd.set('cartoon_fancy_helices', 1)
cmd.set('cartoon_fancy_sheets', 1)

# Render
cmd.ray(2400, 2400)
cmd.png('/path/to/figure.png', dpi=300)
```

### Dramatic Dark Background

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.spectrum('count', 'rainbow', 'all')
cmd.orient()

# Dark theme
cmd.bg_color('black')
cmd.set('ray_trace_mode', 1)
cmd.set('ray_shadows', 'on')
cmd.set('ray_trace_gain', 0.15)
cmd.set('antialias', 2)
cmd.set('depth_cue', 0)
cmd.set('ray_trace_fog', 0)

# Render
cmd.ray(2400, 2400)
cmd.png('/path/to/figure_dark.png', dpi=300)
```

### Transparent Background (for compositing)

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')
cmd.util.cbc()
cmd.orient()

# Transparent background
cmd.set('ray_opaque_background', 'off')
cmd.set('ray_trace_mode', 1)
cmd.set('antialias', 2)

# Render
cmd.ray(2400, 2400)
cmd.png('/path/to/figure_transparent.png', dpi=300)
```

### High-Resolution Surface

```python
cmd.fetch('1ubq')
cmd.show('surface', 'all')
cmd.spectrum('b', 'blue_white_red', 'all')
cmd.orient()

# High quality surface
cmd.set('surface_quality', 2)
cmd.bg_color('white')
cmd.set('ray_trace_mode', 1)
cmd.set('antialias', 2)

# Render
cmd.ray(3000, 3000)
cmd.png('/path/to/surface.png', dpi=300)
```

## Special Representations

### B-factor Visualization

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')

# Color by B-factor (flexibility)
cmd.spectrum('b', 'blue_white_red', 'all')

# Vary cartoon tube radius by B-factor
cmd.cartoon('putty', 'all')
cmd.set('cartoon_putty_scale_min', 0.5)
cmd.set('cartoon_putty_scale_max', 2.0)

cmd.orient()
```

### Secondary Structure Elements

```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.hide('lines', 'all')

# Color by secondary structure
cmd.color('red', 'ss h')  # Helices
cmd.color('yellow', 'ss s')  # Sheets
cmd.color('green', 'ss l+""')  # Loops/coil

cmd.orient()
```

### Hydrophobic Surface

```python
cmd.fetch('1ubq')
cmd.show('surface', 'all')

# Simple hydrophobicity coloring
# Hydrophobic: red, Polar: white, Charged: blue
cmd.color('white', 'all')
cmd.color('red', 'resn ALA+VAL+LEU+ILE+MET+PHE+TRP+PRO')
cmd.color('blue', 'resn ARG+LYS+ASP+GLU')

cmd.orient()
```

## Workflow: Complete Figure Generation

### Step-by-step Publication Figure

```python
# 1. Load structure
cmd.reinitialize()
cmd.fetch('1ubq')

# 2. Basic setup
cmd.hide('everything', 'all')
cmd.show('cartoon', 'polymer.protein')
cmd.show('sticks', 'organic')
cmd.hide('everything', 'solvent')

# 3. Coloring
cmd.color('palegreen', 'polymer.protein')
cmd.util.cnc('organic')

# 4. View
cmd.orient()
cmd.turn('y', 30)

# 5. Settings for publication
cmd.bg_color('white')
cmd.set('cartoon_fancy_helices', 1)
cmd.set('cartoon_fancy_sheets', 1)
cmd.set('cartoon_loop_radius', 0.3)
cmd.set('stick_radius', 0.15)
cmd.set('ray_trace_mode', 1)
cmd.set('antialias', 2)

# 6. Render
cmd.ray(2400, 1800)
cmd.png('/path/to/figure.png', dpi=300)
```

## Tips for Better Figures

### Reduce Clutter
- Hide hydrogen atoms: `cmd.hide('(hydro)')`
- Hide water: `cmd.hide('everything', 'solvent')`
- Use cartoon for protein overview
- Only show sticks for regions of interest

### Improve Aesthetics
- `cmd.set('cartoon_fancy_helices', 1)` - Better helix rendering
- `cmd.set('cartoon_fancy_sheets', 1)` - Arrow-style sheets
- `cmd.set('antialias', 2)` - Smoother edges
- `cmd.set('ray_trace_mode', 1)` - Clean outlines

### Consistent Coloring
- Use `cmd.util.cbc()` for automatic chain colors
- Use `cmd.util.cnc()` to color non-carbons by element
- Keep carbon colors distinct between objects

### Camera Angles
- `cmd.orient()` - Auto-orient to principal axes
- `cmd.turn('x/y/z', angle)` - Fine-tune rotation
- `cmd.zoom('selection', buffer=N)` - Add padding around focus
