import unittest

from height_sample import HeightSample, corner_shade_factor


class HeightShadowTests(unittest.TestCase):
    def test_shadow_falls_east_and_slightly_north(self):
        # Terrain falling toward ENE is the lee/shadow side. The inverse
        # (rising toward ENE) faces the WSW light and must be illuminated.
        falls_ene=HeightSample(0,0,2,2,[[4,2,0],[5,3,1],[6,4,2]])
        rises_ene=HeightSample(0,0,2,2,[[2,4,6],[1,3,5],[0,2,4]])
        shadow=corner_shade_factor(falls_ene,1,1)
        light=corner_shade_factor(rises_ene,1,1)
        self.assertLess(shadow,1.0)
        self.assertGreater(light,1.0)
        self.assertLess(shadow,light)


if __name__ == "__main__":
    unittest.main()
