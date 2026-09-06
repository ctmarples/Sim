"""Permanent field-soil shading, smoothly interpolated and cached by ecology generation."""
import pygame

class FieldFertilityTint:
    def __init__(self):
        self.key = None
        self.surface = None

    def apply(self, base, world, fields, generation, cell_size):
        bounds = tuple(field.plot_bounds() for field in fields)
        key = (id(base), world.terrain_revision, generation, bounds, cell_size)
        if key == self.key:
            return self.surface
        shaded = base.copy()
        for field in fields:
            left, top, right, bottom = field.plot_bounds()
            w, h = right-left+1, bottom-top+1
            # Padded samples avoid artificial dark borders; bilinear resampling
            # interpolates between cell centres with no per-frame sampling.
            samples = pygame.Surface((w+2,h+2), pygame.SRCALPHA)
            for sy in range(h+2):
                for sx in range(w+2):
                    x = max(left,min(right,left+sx-1))
                    y = max(top,min(bottom,top+sy-1))
                    fertility = max(0.,min(1.,world.get_cell(x,y).fertility))
                    samples.set_at((sx,sy), (35,24,12,round(fertility*105)))
            smooth = pygame.transform.smoothscale(samples, ((w+2)*cell_size,(h+2)*cell_size))
            shaded.blit(smooth, (left*cell_size,top*cell_size),
                        pygame.Rect(cell_size,cell_size,w*cell_size,h*cell_size))
        self.key, self.surface = key, shaded
        return shaded
