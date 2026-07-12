# Scientific Methods and Provenance

DBand Studio calculates moments of the selected atoms' VASP projected DOS.
For LORBIT 10, d-band metrics use the aggregate `d` channel. For LORBIT 11,
the total d DOS is the sum of `dxy`, `dyz`, `dz2`, `dxz`, and `dx2-y2`.

The d-band center is the first DOS moment, width is the second-moment standard
deviation, and filling is the occupied DOS fraction with Fermi-edge bin
splitting. Energy range and integration method are part of the result.

Noncollinear/SOC up/down curves are projections reconstructed along VASP's
SAXIS. They are not ordinary collinear spin channels.

CSV exports include source format, reported VASP version, spin mode, orbital
resolution, field source, integration range, and integration method.
