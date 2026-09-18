"""Verify the coverage observer before interpreting game measurements."""

import unittest

from audit_runtime_usage import Recorder, SOURCE


class RecorderTests(unittest.TestCase):
    def test_branch_hits_are_separate_for_startup_and_gameplay(self):
        filename = str(SOURCE / "_audit_test_fixture.py")
        code = compile(
            "def choose(flag):\n"
            "    if flag:\n"
            "        return 1\n"
            "    return 2\n"
            "choose(True)\n",
            filename, "exec",
        )
        recorder = Recorder({filename: {}})
        namespace = {}
        recorder.start()
        try:
            exec(code, namespace)
            self.assertIn(3, recorder.lines[("startup_load", filename)])
            self.assertNotIn(4, recorder.lines[("startup_load", filename)])
            recorder.begin_play()
            self.assertEqual(namespace["choose"](False), 2)
            self.assertIn(4, recorder.lines[("gameplay", filename)])
            self.assertNotIn(3, recorder.lines[("gameplay", filename)])
            self.assertIn(("choose", 1), recorder.functions[("gameplay", filename)])
        finally:
            recorder.stop()

    def test_external_file_is_not_recorded(self):
        filename = str(SOURCE / "_audit_test_fixture.py")
        recorder = Recorder({filename: {}})
        recorder.start()
        try:
            exec(compile("value = 1\n", "/tmp/external_fixture.py", "exec"), {})
        finally:
            recorder.stop()
        self.assertFalse(recorder.lines)
        self.assertFalse(recorder.functions)


if __name__ == "__main__":
    unittest.main()
