"""ANVEL Resilience Agent.

This module hosts a lightweight automation agent that can be started
alongside ANVEL in order to:

* run the repository's verification suite (``scripts/run_pipeline.py test``)
    to ensure dependencies, builds, and core smoke tests succeed
* automatically trigger bootstrap + full pipeline rebuilds when validations
    fail, including file restoration from packaged release archives
* emit an executable fallback script that performs a full bootstrap and
    pipeline run in case primary startup fails
* persist detailed logs + JSON status reports so operators have a single
    place to inspect health and recovery steps

The agent intentionally avoids direct imports from the broader ANVEL codebase
so that it can operate even if application modules fail to import. It only
relies on Python's standard library and the repo's automation scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CommandResult:
    """Represents the outcome of a subprocess invocation."""

    command: List[str]
    success: bool
    returncode: int
    log_path: Path
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the result so it can live inside JSON payloads."""

        return {
            "command": self.command,
            "success": self.success,
            "returncode": self.returncode,
            "log_path": str(self.log_path),
            "summary": self.summary,
        }


class ANVELResilienceAgent:
    """Self-contained validation + recovery helper for the ANVEL stack."""

    CRITICAL_PATHS: Tuple[str, ...] = (
        "ANVEL_MASTER.py",
        "anvel_bootstrap.py",
        "scripts/run_pipeline.py",
        "scripts/package_release.py",
        "test_ultimate_system.py",
        "requirements.txt",
    )

    def __init__(
        self,
        root: Path | None = None,
        python_exec: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.root = Path(root) if root else Path(__file__).resolve().parent
        self.python_exec = python_exec or sys.executable
        self.dry_run = dry_run
        self.backup_dir = self.root / "backups"
        self.log_dir = self.backup_dir / "agent_logs"
        self.report_path = self.backup_dir / "resilience_report.json"
        self.dist_dir = self.root / "dist"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        run_tests: bool = True,
        produce_backup_script: bool = True,
        auto_heal: bool = True,
        restore_missing: bool = True,
    ) -> Dict[str, Any]:
        """Run the agent end-to-end and return structured telemetry."""

        results: Dict[str, Any] = {
            "timestamp": self._iso_timestamp(),
            "root": str(self.root),
            "auto_heal_enabled": auto_heal,
        }

        validation_result: Optional[CommandResult] = None
        final_validation: Optional[CommandResult] = None

        if run_tests:
            validation_result = self._run_validation_suite()
            results["validation"] = validation_result.to_dict()
            final_validation = validation_result

            if auto_heal and not validation_result.success:
                healing_report, healed_validation = self._auto_heal_pipeline(
                    initial_result=validation_result,
                    restore_missing=restore_missing,
                )
                results["healing"] = healing_report
                if healed_validation is not None:
                    final_validation = healed_validation

        if final_validation:
            results["final_validation"] = final_validation.to_dict()

        if produce_backup_script:
            backup_info = self._generate_backup_script()
            results["backup_script"] = {
                "path": str(backup_info),
                "exists": backup_info.exists(),
            }

        self._write_report(results)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_validation_suite(self) -> CommandResult:
        """Invoke the repo's pipeline test stage to verify readiness."""

        pipeline = self.root / "scripts" / "run_pipeline.py"
        cmd = [self.python_exec, str(pipeline), "test"]
        return self._invoke(
            cmd,
            log_name="validation",
            success_summary="Validation suite succeeded",
            failure_summary="Validation suite failed",
        )

    def _auto_heal_pipeline(
        self,
        initial_result: Optional[CommandResult],
        restore_missing: bool,
    ) -> Tuple[Dict[str, Any], Optional[CommandResult]]:
        """Attempt to self-heal by re-running bootstrap + pipeline stages."""

        pipeline = self.root / "scripts" / "run_pipeline.py"
        bootstrap = self._invoke(
            [self.python_exec, str(pipeline), "bootstrap"],
            log_name="heal_bootstrap",
            success_summary="Environment bootstrap completed",
            failure_summary="Environment bootstrap failed",
        )
        full_pipeline = self._invoke(
            [self.python_exec, str(pipeline), "all"],
            log_name="heal_pipeline",
            success_summary="Full pipeline completed",
            failure_summary="Full pipeline failed",
        )

        missing = self._detect_missing_paths()
        restoration: Optional[Dict[str, Any]] = None
        if restore_missing and missing:
            restoration = self._restore_workspace_from_release(missing)

        final_validation = self._run_validation_suite()
        report: Dict[str, Any] = {
            "triggered": True,
            "reason": initial_result.summary if initial_result else "manual",
            "bootstrap": bootstrap.to_dict(),
            "pipeline": full_pipeline.to_dict(),
            "missing_paths": [self._format_relative(p) for p in missing],
            "restoration": restoration,
            "final_validation": final_validation.to_dict(),
        }
        return report, final_validation

    def _detect_missing_paths(self) -> List[Path]:
        missing: List[Path] = []
        for rel in self.CRITICAL_PATHS:
            candidate = self.root / rel
            if not candidate.exists():
                missing.append(candidate)
            elif candidate.is_file() and candidate.stat().st_size == 0:
                missing.append(candidate)
        return missing

    def _restore_workspace_from_release(
        self, targets: List[Path]
    ) -> Optional[Dict[str, Any]]:
        archive = self._latest_release_archive()
        if not archive:
            return {
                "archive": None,
                "restored_paths": [],
                "notes": "No release archives found in dist/",
            }
        extracted_root = self._extract_release_archive(archive)
        restored: List[str] = []
        for target in targets:
            rel = self._format_relative(target)
            source = self._match_release_entry(extracted_root, target)
            if not source:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(
                    source,
                    target,
                    dirs_exist_ok=True,
                )
            else:
                shutil.copy2(source, target)
            restored.append(rel)
        return {
            "archive": str(archive),
            "extracted_to": str(extracted_root),
            "restored_paths": restored,
        }

    def _latest_release_archive(self) -> Optional[Path]:
        if not self.dist_dir.exists():
            return None
        archives = sorted(self.dist_dir.glob("anvel_release_*.zip"))
        return archives[-1] if archives else None

    def _extract_release_archive(self, archive: Path) -> Path:
        destination = (
            self.backup_dir
            / "release_extracts"
            / f"{archive.stem}_{self._log_timestamp()}"
        )
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(destination)
        return destination

    def _match_release_entry(
        self,
        extracted_root: Path,
        target_path: Path,
    ) -> Optional[Path]:
        rel_parts = tuple(target_path.relative_to(self.root).parts)
        rel_len = len(rel_parts)
        for candidate in extracted_root.rglob(target_path.name):
            candidate_parts = candidate.relative_to(extracted_root).parts
            if len(candidate_parts) < rel_len:
                continue
            if candidate_parts[-rel_len:] == rel_parts:
                return candidate
        return None

    def _format_relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def _invoke(
        self,
        cmd: List[str],
        log_name: str,
        success_summary: str | None = None,
        failure_summary: str | None = None,
    ) -> CommandResult:
        """Run a subprocess, capture output, and persist a log file."""

        timestamp = self._log_timestamp()
        log_path = self.log_dir / f"{log_name}_{timestamp}.log"

        if self.dry_run:
            log_path.write_text(f"[DRY-RUN] Would execute: {' '.join(cmd)}{os.linesep}")
            return CommandResult(
                command=cmd,
                success=True,
                returncode=0,
                log_path=log_path,
                summary="Dry-run mode skipped execution.",
            )

        completed = subprocess.run(
            cmd,
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        log_path.write_text(
            f"$ {' '.join(cmd)}{os.linesep}"
            f"--- STDOUT ---{os.linesep}{completed.stdout}{os.linesep}"
            f"--- STDERR ---{os.linesep}{completed.stderr}{os.linesep}"
        )
        summary = success_summary or "Command succeeded"
        if completed.returncode != 0:
            summary = failure_summary or f"{summary} (failed)"
        return CommandResult(
            command=cmd,
            success=completed.returncode == 0,
            returncode=completed.returncode,
            log_path=log_path,
            summary=summary,
        )

    def _generate_backup_script(self) -> Path:
        """Create an executable fallback script for full recovery."""

        script_path = self.backup_dir / "auto_recovery_bootstrap.py"
        content = textwrap.dedent("""\
            #!/usr/bin/env python3
            # Auto-generated fallback bootstrapper (by ANVELResilienceAgent).
            import subprocess
            import sys
            from pathlib import Path

            ROOT = Path(__file__).resolve().parents[1]
            PIPELINE = ROOT / 'scripts' / 'run_pipeline.py'

            def main() -> None:
                cmds = [
                    [sys.executable, str(PIPELINE), 'bootstrap'],
                    [sys.executable, str(PIPELINE), 'all'],
                    [sys.executable, str(PIPELINE), 'launch'],
                ]
                for cmd in cmds:
                    print(f"Executing: {' '.join(cmd)}")
                    subprocess.run(cmd, cwd=ROOT, check=True)

            if __name__ == '__main__':
                main()
            """)
        script_path.write_text(content)
        script_path.chmod(0o755)
        return script_path

    def _write_report(self, payload: Dict[str, object]) -> None:
        """Persist agent telemetry for later troubleshooting."""

        with open(self.report_path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _iso_timestamp(self) -> str:
        return self._utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _log_timestamp(self) -> str:
        return self._utc_now().strftime("%Y%m%d_%H%M%S")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the ANVEL Resilience Agent to validate the deployment and "
            "emit a fallback bootstrap script."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (defaults to this file's parent).",
    )
    parser.add_argument(
        "--python-exec",
        default=None,
        help="Python interpreter to use when calling run_pipeline.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip subprocess execution and just record intentions.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Do not run scripts/run_pipeline.py test.",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Do not regenerate the auto recovery bootstrap script.",
    )
    parser.add_argument(
        "--no-auto-heal",
        dest="auto_heal",
        action="store_false",
        help="Skip automatic self-healing if the validation suite fails.",
    )
    parser.add_argument(
        "--no-restore",
        dest="restore_missing",
        action="store_false",
        help="Do not attempt to rebuild missing files from release archives.",
    )
    parser.set_defaults(auto_heal=True, restore_missing=True)
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    agent = ANVELResilienceAgent(
        root=args.root,
        python_exec=args.python_exec,
        dry_run=args.dry_run,
    )
    results = agent.execute(
        run_tests=not args.skip_tests,
        produce_backup_script=not args.skip_backup,
        auto_heal=args.auto_heal,
        restore_missing=args.restore_missing,
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ANVELResilienceAgent", "CommandResult"]
