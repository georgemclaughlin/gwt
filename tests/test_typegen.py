from pathlib import Path
import unittest

from gwtlang import GwtError, generate_typescript_file, generate_typescript_text


class TypeGenerationTests(unittest.TestCase):
    def test_vendor_onboarding_typescript_example_fixture_is_current(self):
        generated = generate_typescript_file("examples/vendor_onboarding/rules.gwt")
        fixture = Path("clients/typescript/examples/vendor-onboarding.generated.d.ts")

        self.assertEqual(fixture.read_text(), generated.source)

    def test_typescript_generation_rejects_overlapping_contract_paths(self):
        with self.assertRaisesRegex(GwtError, "REQUEST contract path x\\.y overlaps x"):
            generate_typescript_text(
                """
                REQUEST x is text
                AND x.y is number
                """
            )

    def test_typescript_generation_rejects_overlapping_record_field_paths(self):
        with self.assertRaisesRegex(GwtError, "record Foo field path x\\.y overlaps x"):
            generate_typescript_text(
                """
                RECORD Foo
                  x: text
                    y: number

                REQUEST foo is Foo
                """
            )


if __name__ == "__main__":
    unittest.main()
