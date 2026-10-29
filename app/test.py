
# /// script
# requires-python = ">=3.11"
# dependencies = ["arelle-release"]
# ///

import json
import tempfile
import zipfile
import tkinter as tk

from pathlib import Path
from tkinter import filedialog, messagebox
from arelle import Cntlr, PackageManager


def extract_nested_zips(zip_path, destination):
    """Extract a ZIP and recursively extract nested ZIP archives."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)

    processed = set()

    while True:
        nested = [
            p for p in destination.rglob("*.zip")
            if p not in processed
        ]

        if not nested:
            break

        for archive_path in nested:
            processed.add(archive_path)
            target = archive_path.parent / archive_path.stem
            target.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(archive_path) as archive:
                    archive.extractall(target)
                archive_path.unlink()
            except zipfile.BadZipFile:
                print(f"Skipping invalid ZIP: {archive_path}")


def find_taxonomy_packages(directory):
    """Find taxonomy package descriptors recursively."""
    return list(Path(directory).rglob("taxonomyPackage.xml"))


def convert():
    root = tk.Tk()
    root.withdraw()

    try:
        package = filedialog.askopenfilename(
            parent=root,
            title="Select SSM Malaysia Taxonomy ZIP",
            filetypes=[("ZIP files", "*.zip")],
        )
        if not package:
            return

        report = filedialog.askopenfilename(
            parent=root,
            title="Select XBRL report",
            filetypes=[
                ("XBRL files", "*.xbrl *.xml"),
                ("All files", "*.*"),
            ],
        )
        if not report:
            return

        output = filedialog.asksaveasfilename(
            parent=root,
            title="Save JSON output",
            defaultextension=".json",
            initialfile=Path(report).stem + ".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not output:
            return

        controller = Cntlr.Cntlr()
        model = None

        try:
            # Keep extracted taxonomy files available until processing ends.
            with tempfile.TemporaryDirectory(prefix="ssm_taxonomy_") as temp:
                extract_nested_zips(package, temp)

                package_files = find_taxonomy_packages(temp)

                # Register each discovered taxonomy package.
                for descriptor in package_files:
                    PackageManager.addPackage(
                        controller, str(descriptor.parent)
                    )

                # Load the report and resolve its taxonomy references.
                model = controller.modelManager.load(report)

                if model is None or model.modelDocument is None:
                    raise RuntimeError(
                        "Arelle could not load the XBRL report."
                    )

                # Validate the loaded report.
                controller.modelManager.validate()

                facts = []
                for fact in model.facts:
                    concept = fact.concept

                    facts.append({
                        "concept": str(fact.qname),
                        "label": (
                            concept.label(lang="en")
                            if concept else None
                        ),
                        "value": None if fact.isNil else fact.value,
                        "context_ref": fact.contextID,
                        "unit_ref": fact.unitID,
                        "decimals": fact.decimals,
                        "is_nil": fact.isNil,
                    })

                result = {
                    "report": Path(report).name,
                    "taxonomy_package": Path(package).name,
                    "packages_discovered": len(package_files),
                    "fact_count": len(facts),
                    "facts": facts,
                    "validation_errors": [
                        str(error) for error in model.errors
                    ],
                }

                Path(output).write_text(
                    json.dumps(result, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            messagebox.showinfo(
                "Success",
                f"JSON saved successfully:\n{output}",
                parent=root,
            )

        finally:
            if model is not None:
                model.close()
            controller.close()

    except Exception as exc:
        messagebox.showerror(
            "Conversion failed", str(exc), parent=root
        )
    finally:
        root.destroy()


if __name__ == "__main__":
    convert()
