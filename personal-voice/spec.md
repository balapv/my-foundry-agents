Implement Phase 1 of the Demo Voice Polish tool using the implementation specification in this repository.

Read the full implementation spec before making changes.

The goal of Phase 1 is intentionally narrow: prove that we can synthesize speech programmatically using my Azure Speech Personal Voice, save it as a WAV file, measure its actual duration, and compare that duration with a target.

Use this configuration:

- Azure Speech region: `swedencentral`
- Azure Speech endpoint: `https://balapv-sweden-central-resource.cognitiveservices.azure.com/`
- Personal Voice speaker profile ID: `47a5ed79-98bb-44a9-86e7-e22e957f2bf3`

Do not put credentials or secrets in source control.

Start by determining the current supported Azure Speech API/SDK approach for Personal Voice synthesis. Prefer Microsoft Entra authentication where supported. If the Personal Voice synthesis path requires another authentication mechanism, keep credentials entirely outside source control and document the setup.

Use this as the first acceptance test:

Text:
`This is a native voice agent in Microsoft Foundry.`

Target duration:
`4.0 seconds`

The generated speech must use my Personal Voice. Do not silently substitute a standard Azure neural voice if Personal Voice synthesis fails.

Implement:

1. Personal Voice text-to-speech synthesis.
2. WAV output.
3. Programmatic WAV duration measurement.
4. Target-versus-actual timing comparison.
5. Clear error handling.
6. Externalized configuration.
7. README setup and run instructions.
8. The validation tests defined in the implementation specification.

Keep the implementation simple and focused.

Do not implement rate optimization, script rewriting, SRT parsing, video processing, FFmpeg integration, MP4 manipulation, or any Phase 2/3 functionality.

When implementation is finished:

1. run the tests;
2. run the baseline synthesis if credentials and API access are available in the environment;
3. report exactly what passed and failed;
4. show the actual measured duration of the baseline WAV if synthesis succeeded;
5. identify any remaining setup or access requirement;
6. do not proceed to Phase 2.

If you encounter an Azure API or SDK ambiguity, verify the current Microsoft documentation rather than guessing.
