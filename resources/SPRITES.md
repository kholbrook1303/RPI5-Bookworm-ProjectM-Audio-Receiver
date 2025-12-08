## User Sprites
As of version 4.2, libprojectM supports rendering of Milkdrop user sprites.

There are two key differences to how Milkdrop parses and displays sprites:

1. The projectM sprite API only takes a single sprite as code in the API function. Applications using projectM therefore must read any pre-existing sprites INI file and split it up using the `[imgNN]` section headers. Passing the actual section header is supported, but completely optional as it is ignored by projectM.
2. projectM does not support color keys with blend mode 4. Color keyed textures is a feature solely supported by DirectX. As projectM uses OpenGL, reimplementing this feature wasn't worth the effort. Instead, blend mode 4 in projectM will use the texture alpha channel for transparency. This is even superior to color keying as it allows smooth transparency gradients.

In future releases, additional sprite types might be supported. The API expects a type string to determine the sprite variant, with `milkdrop` currently being the only supported type. Trying to show a sprite with an unknown type name will simply be ignored by the library, not causing any issues except for the sprite not being displayed.

## Milkdrop Sprite Definition File Format
The sprite def file is very similar to the .milk preset format, as it also uses INI syntax. Each sprite is defined in its own section named `[imgXX]`, where `XX` is a two-digit number. Each section can contain the following lines:

- `img = <filename>`: The sprite texture image to load.
- `colorkey = 0xAARRGGBB`: Transparency color key. Defaults to black, alpha is always set to 0xFF in Milkdrop. Might not work using the hexadecimal representation as Milkdrop uses `GetPrivateProfileInt()`, which doesn't support parsing 0x... values.
- `init_N = <code>`: Initialization expression, run once after loading the sprite. `N` is the line number, starting with 1. Numbering must be continuous. Each line of `<code>` is appended and executed as one program.
`code_N = <code>`: Per-frame expression, run once every time the sprite is drawn. `N` is the line number, starting with 1. Numbering must be continuous. Each line of `<code>` is appended and executed as one program.

The following expression variables are available in the code_N expressions, updated with the current frame data:

- `time`: Time passed since program start. Also available in init code.
- `frame`: Total frames rendered so far. Also available in init code.
- `fps`: Current (or, if not available, target) frames per second value.
- `progress`: Preset blending progress (only if blending).
- `bass`: Bass frequency loudness, median of 1.0, range of ~0.7 to ~1.3 in most cases.
- `mid`: Middle frequency loudness, median of 1.0, range of ~0.7 to ~1.3 in most cases.
- `treb`: Treble frequency loudness, median of 1.0, range of ~0.7 to ~1.3 in most cases.
- `bass_att`: More attenuated/smoothed value of bass.
- `mid_att`: More attenuated/smoothed value of mid.
- `treb_att`: More attenuated/smoothed value of treb.

The following output variables are used to draw the sprite:

- `done`: If this becomes non-zero, the sprite is deleted. Default: 0.0
- `burn`: If non-zero, the sprite will be "burned" into currently rendered presets when `done` is also true, effectively "dissolving" the sprite in the preset. Default: 1.0
- `x`, `y`: Sprite x/y position (position of the image center). Range from -1000 to 1000. Default: 0.5
- `sx`, `sy`: Sprite x/y scaling factor. Range from -1000 to 1000. Default: 1.0
- `rot`: Sprite rotation in radians (2*PI equals one full rotation). Default: 0.0
- `flipx`, `flipy`: If a flag is non-zero, the sprite is flipped in this axis. Default: 0.0
- `repeatx`, `repeaty`: Repeat count of the image on the sprite quad. Fractional values allowed. Range from 0.01 to 100.0. Default: 1.0
- `blendmode`: Image blending mode. 0 = Alpha blending (default), 1 = Decal mode (no transparency), 2 = Additive blending, 3 = Source color blending, 4 = Color key blending. Default: 0
- `r`, `g`, `b`, `a`: Modulation color used in some blending modes. Default: 1.0

Default values are used if the expressions don't explicitly set a value. No `q` or `t` variables are available to sprite expressions. The `regXX` vars, `gmegabuf` and `megabuf` are individual per-sprite contents, not shared between sprites or with any running presets.

The blending modes are using this "effect" matrix:
```
// blendmodes                                      src alpha:        dest alpha:
// 0   blend      r,g,b=modulate     a=opacity     SRCALPHA          INVSRCALPHA
// 1   decal      r,g,b=modulate     a=modulate    D3DBLEND_ONE      D3DBLEND_ZERO
// 2   additive   r,g,b=modulate     a=modulate    D3DBLEND_ONE      D3DBLEND_ONE
// 3   srccolor   r,g,b=no effect    a=no effect   SRCCOLOR          INVSRCCOLOR
// 4   col
```

## Milkdrop3 to projectM Sprite Equivalents (Effects)

### Zoom Level 1
```
[img00]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1=sx = 1.0 + 0.1 * sin(time * 0.8);
code_2=sy = 1.0 + 0.1 * sin(time * 0.8);
```

### Zoom Level 2
```
[img01]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1 = sx = 0.9 + 0.2 * sin(time * 0.9);
code_2 = sy = 0.9 + 0.2 * sin(time * 0.9);
```

### Zoom Level 3
```
[img02]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1 = sx = 0.8 + 0.5 * sin(time * 0.9);
code_2 = sy = 0.8 + 0.5 * sin(time * 0.9);
```

### Beats Level 1
```
[img03]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1=sx = 1.0 + 0.05 * (bass - 1.0);
code_2=sy = 1.0 + 0.05 * (bass - 1.0);
code_3=rot = 0;
```

### Beats Level 2
```
[img04]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1=sx = 0.9 + 0.1 * (bass - 1.0);
code_2=sy = 0.9 + 0.1 * (bass - 1.0);
code_3=rot = 0;
```

### Beats Level 3
```
[img05]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
init_2=sx = 1.5;
init_3=sy = 1.5;
code_1=sx = 1.5 + 0.2 * (bass - 1.0);
code_2=sy = 1.5 + 0.2 * (bass - 1.0);
code_3=rot = 0;
```

### Cercles Level 1
```
[img06]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1 = x = 0.5 + 0.05 * cos(time * 1.5);
code_2 = y = 0.5 + 0.05 * sin(time * 1.5);
```

### Cercles Level 2
```
[img07]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1 = x = 0.5 + 0.05 * cos(time * 2.0);
code_2 = y = 0.5 + 0.05 * sin(time * 2.0);
```

### Cercles Level 3
```
[img08]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
code_1 = x = 0.5 + 0.05 * cos(time * 2.5);
code_2 = y = 0.5 + 0.05 * sin(time * 2.5);
```

### Alpha Level 1
```
[img09]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
init_2 = a = 0.0;
code_1 = level = 0.33 * bass_att + 0.33 * mid_att + 0.5 * treb_att;
code_2 = a = 0.4 + 0.5 * (level - 1.0);
```

### Alpha Level 2
```
[img10]
img=logo
colorkey=0x000000
init_1=blendmode = 4;
init_2 = a = 0.0;
code_1 = level = 0.33 * bass_att + 0.33 * mid_att + 0.5 * treb_att;
code_2 = a = 0.2 + 1.0 * (level - 1.0);
```

### Alpha Level 3
```
[img11]
img=logo
colorkey=0x2F2F2F
init_1=blendmode = 4;
init_2 = a = 0.0;
code_1 = level = 0.33 * bass_att + 0.33 * mid_att + 0.5 * treb_att;
code_2 = a = 1.5 * (level - 1.0);
```