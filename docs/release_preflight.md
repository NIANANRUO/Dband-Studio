# Release preflight

Do not distribute an installer until every check below passes from the exact
commit being released.

1. Run the full source test suite:

   ```powershell
   C:\Users\21483\.conda\envs\lis_sac_ml\python.exe -m pytest -q
   ```

2. Build with `installer/dband_studio.spec` and run the frozen executable's
   non-GUI dependency check:

   ```powershell
   .\dist\DBandStudio\DBandStudio.exe --runtime-self-check
   ```

   Exit code `0` is required.  This executes SciPy Simpson, SciPy special,
   pymatgen periodic-table data, and lxml XML parsing inside the frozen bundle.

3. Confirm that `pymatgen/core/periodic_table.json.gz` and
   `scipy/special/_ufuncs_cxx*.pyd` exist under `dist/DBandStudio/_internal`.

4. For every sample calculation used in a release demonstration, record the
   exact file path, atom selection, spin mode, range, and integration method.
   Never compare a visible old plot after source/atom/orbital controls changed;
   generate a new analysis first.

5. Build the installer only after steps 1–4.  The installer version must match
   `pyproject.toml` and the corresponding Git tag.
