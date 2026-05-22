import unittest

from app.ramair_channel import (
    BINDING_COMMAND,
    NEXT_AUTOMATION,
    RAMAIR_PROJECT_ID,
    STANDARD_NATHAN_PROMPTS,
    STARTER_ARTIFACTS,
    STARTER_FOLDERS,
    binding_status_from_env,
    render_ramair_channel_pilot,
)
from scripts.ramair_channel_pilot import bind_ramair_channel_from_env, render_binding_result


class RamAirChannelPilotTests(unittest.TestCase):
    def test_channel_pilot_has_standard_structure_and_prompts(self):
        folder_paths = [folder["path"] for folder in STARTER_FOLDERS]
        artifact_paths = [artifact["path"] for artifact in STARTER_ARTIFACTS]
        prompt_names = [prompt["name"] for prompt in STANDARD_NATHAN_PROMPTS]

        self.assertEqual(
            folder_paths,
            [
                "00_Client_Brief",
                "01_Source_Material",
                "02_Planning",
                "03_Deliverables",
                "04_Approvals",
                "05_Performance",
            ],
        )
        self.assertIn("client_artifacts/ramair/05_Performance/performance-snapshot.md", artifact_paths)
        self.assertIn("Project Status", prompt_names)
        self.assertIn("Approvals", prompt_names)
        self.assertIn("Interviews", prompt_names)
        self.assertIn("Metrics", prompt_names)
        self.assertIn("Weekly Update", prompt_names)

    def test_binding_status_reports_exact_teams_command_when_ids_missing(self):
        status = binding_status_from_env({})

        self.assertFalse(status["configured"])
        self.assertEqual(status["missing"], ["RAMAIR_TEAMS_TEAM_ID", "RAMAIR_TEAMS_CHANNEL_ID"])
        self.assertEqual(status["command"], BINDING_COMMAND)
        self.assertIn("Select Posts", status["in_teams_path"])

    def test_bind_script_blocks_without_real_teams_ids(self):
        result = bind_ramair_channel_from_env({})
        rendered = render_binding_result(result)

        self.assertEqual(result["status"], "blocked")
        self.assertIn("Missing real Teams identifiers", result["reason"])
        self.assertIn(BINDING_COMMAND, rendered)

    def test_rendered_pilot_mentions_project_and_next_automation(self):
        rendered = render_ramair_channel_pilot()

        self.assertIn(RAMAIR_PROJECT_ID, rendered)
        self.assertIn("Standard Nathan Prompts", rendered)
        self.assertIn(NEXT_AUTOMATION["title"], rendered)


if __name__ == "__main__":
    unittest.main()
