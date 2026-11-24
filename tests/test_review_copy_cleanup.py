import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from shared import common as c
from material_preparation.cleanup_review_copies import plan_copies


class ReviewCopyCleanupTests(unittest.TestCase):
    def test_only_recorded_unchanged_copies_are_eligible(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(c,'ROOT',Path(temp)):
            review=Path(temp)/'material_preparation/review';root=review/'resumes'
            target=root/'Example/R01.txt';target.parent.mkdir(parents=True);target.write_bytes(b'- Copy.')
            raw=Path(temp)/'material_preparation/drafts/occupations/Example/resumes/R01.txt'
            raw.parent.mkdir(parents=True);raw.write_bytes(b'1. Copy.')
            item={'target':str(target),'raw':str(raw),'sha256':c.sha256(target.read_bytes()),'raw_sha256':c.sha256(raw.read_bytes())}
            plan_copies(review,{'files':[item]})
            extra=root/'manual.txt';extra.write_bytes(b'User text')
            with self.assertRaisesRegex(ValueError,'未登记'):plan_copies(review,{'files':[item]})
            extra.unlink();target.write_bytes(b'User changed copy')
            with self.assertRaisesRegex(ValueError,'人工修改'):plan_copies(review,{'files':[item]})
            self.assertEqual(raw.read_bytes(),b'1. Copy.')


if __name__=='__main__':unittest.main()
