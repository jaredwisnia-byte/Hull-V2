"""Native exchange round-trip: trim holes, units, and rejection of bad fits."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from propkit import cad_export, spline_surface


@unittest.skipUnless(cad_export.available(), 'optional Open CASCADE runtime unavailable')
class CadExportTests(unittest.TestCase):
    def document(self):
        mask = np.ones((24, 32), bool)
        mask[8:16, 12:20] = False
        fit = spline_surface.fit_height(np.zeros(mask.shape), mask, 1e-5)
        return spline_surface.document(fit, [0, 0, 0], [.2, 0, 0], [0, .3, 0], [0, 0, 1])

    def test_step_round_trip_preserves_hole_and_metric_units(self):
        from OCP.STEPControl import STEPControl_Reader
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        document = self.document()

        def area(loop):
            p = np.asarray(loop)
            return abs(float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - p[:, 1] * np.roll(p[:, 0], -1))) / 2)
        expected = sum(area(outer) - sum(area(hole) for hole in holes)
                       for outer, holes in cad_export.loop_groups(document['trim_loops_uv'])) * 200 * 300
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'surface.step'
            report = cad_export.export_step([document], path)
            self.assertFalse(report['closed_solid'])
            reader = STEPControl_Reader()
            self.assertEqual(reader.ReadFile(str(path)), IFSelect_RetDone)
            self.assertTrue(reader.TransferRoots())
            shape = reader.OneShape()
            self.assertTrue(BRepCheck_Analyzer(shape).IsValid())
            properties = GProp_GProps()
            BRepGProp.SurfaceProperties_s(shape, properties, 1e-9)
            self.assertAlmostEqual(properties.Mass(), expected, delta=.01)
            self.assertLess(expected, 60000)

    def test_rejected_fit_cannot_be_exported(self):
        document = self.document()
        document['fit']['accepted'] = False
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'out-of-tolerance'):
                cad_export.export_step(
                    [document], Path(temporary) / 'bad.step')


if __name__ == '__main__':
    unittest.main()
