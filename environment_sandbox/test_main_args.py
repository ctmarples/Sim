import unittest

from main import build_parser


class MainArgumentTests(unittest.TestCase):
    def test_new_resource_grid_is_default(self):
        args = build_parser().parse_args([])
        self.assertFalse(args.original_resource_grid)

    def test_original_resource_grid_flag(self):
        for flag in ("--original-resource-grid", "--original-grid", "--original"):
            with self.subTest(flag=flag):
                args = build_parser().parse_args([flag])
                self.assertTrue(args.original_resource_grid)


if __name__ == "__main__":
    unittest.main()
