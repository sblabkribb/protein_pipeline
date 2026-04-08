# PyMOL Command Reference

## Overview

PyMOL commands are accessed through the `cmd` module. When using claudemol, send Python code strings that call `cmd.*` functions.

## Loading Structures

### cmd.load()

Load structure from file:

```python
cmd.load('/path/to/structure.pdb')
cmd.load('/path/to/structure.cif')
cmd.load('/path/to/structure.mol2')
cmd.load('/path/to/structure.sdf')

# With custom object name
cmd.load('/path/to/structure.pdb', 'my_protein')
```

### cmd.fetch()

Fetch from online databases:

```python
# From RCSB PDB
cmd.fetch('1ubq')
cmd.fetch('6lu7', type='pdb')
cmd.fetch('7bv2', type='cif')

# Custom object name
cmd.fetch('1ubq', 'ubiquitin')
```

### cmd.save()

Save structures and sessions:

```python
cmd.save('/path/to/output.pdb', 'my_protein')
cmd.save('/path/to/output.cif', 'all')
cmd.save('/path/to/session.pse')  # Save session
```

## Representations

### cmd.show()

Display representations:

```python
# Basic representations
cmd.show('cartoon', 'all')
cmd.show('surface', 'chain A')
cmd.show('sticks', 'resn LIG')
cmd.show('spheres', 'name CA')
cmd.show('ribbon', 'all')
cmd.show('lines', 'all')
cmd.show('mesh', 'chain A')
cmd.show('dots', 'all')

# Organic (balls and sticks for ligands)
cmd.show('sticks', 'organic')
cmd.show('spheres', 'organic')
```

### cmd.hide()

Hide representations:

```python
cmd.hide('lines', 'all')
cmd.hide('everything', 'solvent')
cmd.hide('cartoon', 'chain B')
cmd.hide('(hydro)')  # Hide hydrogens
```

### cmd.as_()

Show only one representation (hides others):

```python
cmd.as_('cartoon', 'all')
cmd.as_('surface', 'chain A')
```

## Coloring

### cmd.color()

Apply colors:

```python
# Named colors
cmd.color('red', 'chain A')
cmd.color('blue', 'chain B')
cmd.color('green', 'resn LIG')
cmd.color('yellow', 'resi 50-100')
cmd.color('cyan', 'name CA')
cmd.color('white', 'all')

# Hex colors
cmd.color('0xFF5733', 'chain A')

# Common color names:
# red, green, blue, yellow, cyan, magenta, white, black,
# orange, pink, purple, gray, salmon, slate, forest,
# deepblue, deeppurple, lime, tv_red, tv_green, tv_blue
```

### cmd.util.cbc()

Color by chain (automatic):

```python
cmd.util.cbc()  # Color all chains
cmd.util.cbc('my_protein')  # Color specific object
```

### cmd.spectrum()

Gradient coloring:

```python
# Rainbow N to C terminus
cmd.spectrum('count', 'rainbow', 'all')

# B-factor coloring
cmd.spectrum('b', 'blue_white_red', 'all')
cmd.spectrum('b', 'yellow_cyan_blue', 'all')

# Custom range
cmd.spectrum('b', 'blue_white_red', 'all', minimum=20, maximum=80)

# By residue number
cmd.spectrum('resi', 'rainbow', 'chain A')
```

### cmd.set_color()

Define custom colors:

```python
cmd.set_color('my_blue', [0.2, 0.4, 0.8])
cmd.set_color('my_orange', [1.0, 0.5, 0.0])
cmd.color('my_blue', 'chain A')
```

## Selections

### cmd.select()

Create named selections:

```python
# Basic selections
cmd.select('site', 'resi 145')
cmd.select('helix1', 'resi 10-25')
cmd.select('ligand', 'resn LIG')
cmd.select('chainA', 'chain A')

# Distance-based
cmd.select('binding_site', 'byres resn LIG around 5')
cmd.select('interface', 'chain A within 4 of chain B')

# Combining selections
cmd.select('active', 'resi 145+41+166')
cmd.select('no_water', 'all and not solvent')
cmd.select('protein_only', 'polymer.protein')
```

### Selection Syntax

| Expression | Meaning |
|------------|---------|
| `all` | All atoms |
| `chain A` | Chain A |
| `resi 100` | Residue number 100 |
| `resi 10-50` | Residues 10 to 50 |
| `resi 10+20+30` | Specific residues |
| `resn ALA` | All alanines |
| `resn LIG` | Residue named LIG (often ligands) |
| `name CA` | Alpha carbons |
| `name N+CA+C+O` | Backbone atoms |
| `polymer.protein` | Protein chains only |
| `organic` | Organic molecules (ligands) |
| `solvent` | Water molecules |
| `hetatm` | HETATM records |
| `not X` | Everything except X |
| `X and Y` | Intersection |
| `X or Y` | Union |
| `X within 5 of Y` | Atoms within 5A of Y |
| `byres X` | Complete residues containing X |
| `byresidue X` | Same as byres |
| `backbone` | Backbone atoms |
| `sidechain` | Sidechain atoms |

## View Control

### cmd.orient()

Auto-orient view:

```python
cmd.orient()  # All objects
cmd.orient('chain A')  # Specific selection
```

### cmd.zoom()

Zoom to selection:

```python
cmd.zoom('all')
cmd.zoom('chain A')
cmd.zoom('resn LIG', buffer=5)  # With padding
cmd.zoom('resi 50-100')
```

### cmd.center()

Center on selection:

```python
cmd.center('resn LIG')
cmd.center('chain A')
```

### cmd.turn() and cmd.rotate()

Rotate view:

```python
cmd.turn('x', 90)  # Rotate 90 degrees around X
cmd.turn('y', 45)
cmd.turn('z', 30)
```

### cmd.set_view() and cmd.get_view()

Save and restore views:

```python
# Get current view (18 values)
view = cmd.get_view()

# Set view
cmd.set_view([
    1.0, 0.0, 0.0,
    0.0, 1.0, 0.0,
    0.0, 0.0, 1.0,
    0.0, 0.0, -50.0,
    0.0, 0.0, 0.0,
    10.0, 100.0, -20.0
])
```

### cmd.view()

Store and recall named views:

```python
cmd.view('front', 'store')
cmd.view('front', 'recall')
```

## Ray Tracing and Export

### cmd.ray()

Render high-quality image:

```python
# Basic ray trace
cmd.ray()

# Specific resolution
cmd.ray(1920, 1080)
cmd.ray(2400, 2400)  # Square
cmd.ray(4000, 3000)  # High resolution
```

### cmd.png()

Save image:

```python
cmd.png('/path/to/output.png')
cmd.png('/path/to/output.png', dpi=300)
cmd.png('/path/to/output.png', width=1920, height=1080)
```

### Ray Trace Settings

```python
# Ray trace mode
cmd.set('ray_trace_mode', 0)  # Default
cmd.set('ray_trace_mode', 1)  # Cleaner edges
cmd.set('ray_trace_mode', 2)  # Black outline
cmd.set('ray_trace_mode', 3)  # Quantized colors

# Quality settings
cmd.set('antialias', 2)  # 0-4, higher = smoother
cmd.set('ray_shadows', 'on')
cmd.set('ray_trace_gain', 0.1)  # Contrast

# Transparency
cmd.set('ray_trace_fog', 0)
cmd.set('depth_cue', 0)
```

## Display Settings

### cmd.set()

Modify settings:

```python
# Background
cmd.set('bg_rgb', [1, 1, 1])  # White
cmd.set('bg_rgb', [0, 0, 0])  # Black

# Cartoon appearance
cmd.set('cartoon_fancy_helices', 1)
cmd.set('cartoon_fancy_sheets', 1)
cmd.set('cartoon_loop_radius', 0.2)
cmd.set('cartoon_tube_radius', 0.5)
cmd.set('cartoon_oval_width', 0.25)

# Surface
cmd.set('surface_quality', 1)
cmd.set('transparency', 0.5, 'chain A')

# Sticks/spheres
cmd.set('stick_radius', 0.2)
cmd.set('sphere_scale', 0.3)

# Labels
cmd.set('label_size', 20)
cmd.set('label_color', 'black')
```

### cmd.bg_color()

Set background color:

```python
cmd.bg_color('white')
cmd.bg_color('black')
cmd.bg_color('gray')
```

## Object Management

### cmd.delete()

Remove objects:

```python
cmd.delete('all')
cmd.delete('my_protein')
```

### cmd.disable() / cmd.enable()

Toggle visibility:

```python
cmd.disable('chain B')  # Hide
cmd.enable('chain B')   # Show
```

### cmd.copy()

Duplicate objects:

```python
cmd.copy('protein_copy', 'my_protein')
```

### cmd.extract()

Create new object from selection:

```python
cmd.extract('ligand_obj', 'resn LIG')
cmd.extract('chainA', 'chain A')
```

## Measurements

### cmd.distance()

Measure distance:

```python
cmd.distance('dist1', 'resi 50 and name CA', 'resi 100 and name CA')
```

### cmd.angle()

Measure angle:

```python
cmd.angle('ang1', 'atom1', 'atom2', 'atom3')
```

### cmd.dihedral()

Measure dihedral:

```python
cmd.dihedral('dih1', 'atom1', 'atom2', 'atom3', 'atom4')
```

## Alignment and Superposition

### cmd.align()

Sequence-based alignment:

```python
cmd.align('mobile', 'target')
cmd.align('1ubq', '1ubi')
```

### cmd.super()

Structure-based superposition:

```python
cmd.super('mobile', 'target')
```

### cmd.cealign()

CE alignment:

```python
cmd.cealign('target', 'mobile')
```

## Utility Commands

### cmd.reinitialize()

Reset PyMOL:

```python
cmd.reinitialize()
```

### cmd.refresh()

Refresh display:

```python
cmd.refresh()
```

### cmd.sync()

Wait for operations to complete:

```python
cmd.sync()
```

## Common Color Names

| Color | RGB Approximate |
|-------|-----------------|
| red | 1.0, 0.0, 0.0 |
| green | 0.0, 1.0, 0.0 |
| blue | 0.0, 0.0, 1.0 |
| yellow | 1.0, 1.0, 0.0 |
| cyan | 0.0, 1.0, 1.0 |
| magenta | 1.0, 0.0, 1.0 |
| white | 1.0, 1.0, 1.0 |
| black | 0.0, 0.0, 0.0 |
| orange | 1.0, 0.5, 0.0 |
| purple | 0.5, 0.0, 0.5 |
| salmon | 1.0, 0.6, 0.6 |
| slate | 0.5, 0.5, 1.0 |
| forest | 0.1, 0.5, 0.1 |
| gray | 0.5, 0.5, 0.5 |
| tv_red | Bright red |
| tv_green | Bright green |
| tv_blue | Bright blue |
