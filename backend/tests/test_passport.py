"""Check that different poll labels retain a shared choice ID and tally."""
import unittest

from features import polls


class ReplyLabelsTest(unittest.TestCase):
    def test_one_poll_has_localized_choices(self):
        kn = polls.reply_buttons(7, "poll", polls.POLL_OPTIONS, "kn-IN")
        hi = polls.reply_buttons(7, "poll", polls.POLL_OPTIONS, "hi-IN")
        self.assertEqual(kn[0], ("poll:7:0", "ಹೌದು"))
        self.assertEqual(hi[0], ("poll:7:0", "हाँ"))
        self.assertEqual([button[0] for button in kn], [button[0] for button in hi])

    def test_custom_and_legacy_options_are_preserved(self):
        self.assertEqual(polls.reply_buttons(3, "poll", ["Friday", "Saturday"], "kn-IN")[1],
                         ("poll:3:1", "Saturday"))
        self.assertEqual(polls.reply_buttons(3, "task", polls.TASK_OPTIONS, "ta-IN")[0][1],
                         polls.TASK_OPTIONS[0])
