import unittest

from features.watch import summarize


class WatchTest(unittest.TestCase):
    def test_disputed_amount_stays_visible(self):
        item = summarize("  galat hai,\n350 tha  ", "voice")
        self.assertIn("350", item["gist"])
        self.assertEqual(item["tone"], "Needs review")

    def test_explicit_urgency_in_three_scripts(self):
        for phrase in ["jaldi bhejo", "जल्दी भेजो", "ಬೇಗ ಕಳುಹಿಸಿ"]:
            self.assertEqual(summarize(phrase, "text")["tone"], "Urgent wording")

    def test_plain_and_untranscribed_messages(self):
        self.assertEqual(summarize("thank you", "text")["tone"], "Routine")
        self.assertEqual(summarize("", "voice")["tone"], "Unclassified")
        self.assertLessEqual(len(summarize("x" * 120, "text")["gist"]), 75)

    def test_button_is_a_response(self):
        self.assertEqual(summarize("Yes", "button")["tone"], "Response")

    def test_review_status_uses_speakers_words(self):
        self.assertEqual(summarize("", "voice", {"review_status": "pending"})["tone"], "Needs review")
        reviewed = {"review_status": "used", "reviewed_text": "galat hai, 350 tha"}
        self.assertIn("350", summarize("heard 50", "voice", reviewed)["gist"])
        self.assertEqual(summarize("", "voice", {"review_status": "discarded"})["tone"], "Discarded")
