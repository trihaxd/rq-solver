"""Unittest regression suite for the required B2 inventory midterm cases."""
import math
import unittest
from rq_solver import EXAMPLES, Inputs, build_distribution, solve_rq, SolverError
from webapp import solve_payload


def case(index):
    s=list(EXAMPLES.values())[index]
    return Inputs(D=s['D'], A=s['A'], h=s['h'], p=s['p'],
                  lead_time=s['lead_time'], v=s['v'],
                  dist=build_distribution(s['dist_name'], s['dist_params']))

class MidtermRegression(unittest.TestCase):
    def test_hw1_first_three_iterations(self):
        r=solve_rq(case(0),max_iter=3)
        self.assertFalse(r.converged)
        self.assertEqual(len(r.iterations),3)
        self.assertAlmostEqual(r.Q,81.3181676284,places=7)
        self.assertAlmostEqual(r.r,112.5568692457,places=7)
        self.assertAlmostEqual(r.iterations[0].Q,74.8331477355,places=5)
        self.assertAlmostEqual(r.iterations[0].Q_next,80.743324,places=5)

    def test_hw1_converges_and_satisfies_equations(self):
        inp=case(0);r=solve_rq(inp)
        self.assertTrue(r.converged)
        self.assertAlmostEqual(r.Q,81.3228359325,places=7)
        self.assertAlmostEqual(r.r,112.5521995825,places=7)
        self.assertAlmostEqual(r.safety_stock,22.0906611209,places=7)
        lhs=1-inp.dist.cdf(r.r);rhs=r.Q*inp.h/(inp.p*inp.D)
        self.assertLess(abs(lhs-rhs),1e-8)

    def test_hw2_converges(self):
        inp=case(1);r=solve_rq(inp)
        self.assertTrue(r.converged)
        self.assertAlmostEqual(r.Q,102.1710358143,places=7)
        self.assertAlmostEqual(r.r,204.6559756284,places=7)

    def test_gui_payload_uses_same_solver(self):
        s=list(EXAMPLES.values())[0]
        data={'D':s['D'],'A':s['A'],'h':s['h'],'p':s['p'],
              'lead_time':14,'v':s['v'],'base_unit':'year','lead_unit':'week',
              'dist':{'name':'Normal','params':s['dist_params']},
              'derive':s['derive'],'max_iter':3}
        out=solve_payload(data)
        self.assertTrue(out['ok']);self.assertEqual(len(out['iterations']),3)
        self.assertAlmostEqual(out['answer']['Q'],solve_rq(case(0),max_iter=3).Q,places=9)

    def test_bad_lead_time_rejected(self):
        inp=case(0);inp.lead_time=-1
        with self.assertRaises(SolverError):solve_rq(inp)


# Additional checks for the midterm interface updates (appended so that the
# original five tests remain untouched).
class MidtermUpdates(unittest.TestCase):
    def test_zero_tolerance_means_exact_iteration_cap(self):
        from rq_solver import solve_rq
        res = solve_rq(case(0), tol=0, max_iter=8)
        self.assertEqual(len(res.iterations), 8)
        self.assertEqual([it.index for it in res.iterations], list(range(8)))
        self.assertFalse(res.converged)
        self.assertAlmostEqual(res.Q, 81.32283, places=4)

    def test_looser_tolerance_is_available(self):
        from rq_solver import solve_rq
        low = solve_rq(case(0), tol=1e-2, max_iter=200)
        high = solve_rq(case(0), tol=1e-8, max_iter=200)
        self.assertTrue(low.converged)
        self.assertTrue(high.converged)
        self.assertLess(len(low.iterations), len(high.iterations))

    def test_three_steps_and_all_summary_rows_in_gui(self):
        s = list(EXAMPLES.values())[0]
        data = {'D':s['D'], 'A':s['A'], 'h':s['h'], 'p':s['p'],
                'lead_time':14, 'v':s['v'], 'base_unit':'year', 'lead_unit':'week',
                'dist':{'name':'Normal','params':s['dist_params']},
                'derive':s['derive'], 'max_iter':8, 'tol':0}
        result = solve_payload(data)
        self.assertEqual(len(result['iterations']), 8)
        self.assertEqual([x['index'] for x in result['steps_by_iteration']], [0, 1, 2])
        for x in result['steps_by_iteration']:
            self.assertGreater(len(x['steps']), 3)
            self.assertTrue(all('plain' in step for step in x['steps']))

    def test_export_xlsx_is_real_excel_with_full_history(self):
        import io
        import zipfile
        from excel_export import export_bytes
        s = list(EXAMPLES.values())[0]
        data = {'D':s['D'], 'A':s['A'], 'h':s['h'], 'p':s['p'],
                'lead_time':14, 'v':s['v'], 'base_unit':'year', 'lead_unit':'week',
                'dist':{'name':'Normal','params':s['dist_params']},
                'derive':s['derive'], 'max_iter':8, 'tol':0}
        payload = solve_payload(data)
        blob = export_bytes(payload)
        with zipfile.ZipFile(io.BytesIO(blob)) as book:
            self.assertIn('xl/workbook.xml',book.namelist())
            self.assertIn('xl/worksheets/sheet4.xml',book.namelist())
            sheet = book.read('xl/worksheets/sheet4.xml').decode('utf-8')
            # row 1 = header, rows 2..9 = eight iterations
            self.assertIn('r="9"',sheet)
            self.assertIn('81.318', sheet)  # full-precision number around this value

    def test_metadata_new_tolerance_choices(self):
        from webapp import meta_payload
        m = meta_payload()
        self.assertIn(0,m['tolerances'])
        self.assertIn(1e-2,m['tolerances'])
        self.assertEqual(m['default_tolerance'],1e-2)

class MidtermExcelFallback(unittest.TestCase):
    def test_standard_library_xlsx_is_valid_package(self):
        import io
        import zipfile
        import xml.etree.ElementTree as ET
        from excel_export import _stdlib_xlsx
        from webapp import solve_payload
        s=list(EXAMPLES.values())[0]
        data={'D':s['D'],'A':s['A'],'h':s['h'],'p':s['p'],
              'lead_time':14,'v':s['v'],'base_unit':'year','lead_unit':'week',
              'dist':{'name':'Normal','params':s['dist_params']},
              'derive':s['derive'],'tol':0,'max_iter':3}
        buf=_stdlib_xlsx(solve_payload(data))
        with zipfile.ZipFile(io.BytesIO(buf)) as z:
            self.assertIn('[Content_Types].xml', z.namelist())
            self.assertIn('xl/worksheets/sheet4.xml',z.namelist())
            for name in z.namelist():
                if name.endswith('.xml') or name.endswith('.rels'):
                    ET.fromstring(z.read(name))

class DisplayOnlyIterationLimitTests(unittest.TestCase):
    """Regression: detailed working must not truncate the solver or summary."""

    def _payload(self, *, tol=1e-8, max_iter=20):
        spec = list(EXAMPLES.values())[0]
        return solve_payload({'D':spec['D'], 'A':spec['A'], 'h':spec['h'],
                              'p':spec['p'], 'lead_time':14, 'v':spec['v'],
                              'base_unit':'year', 'lead_unit':'week',
                              'dist':{'name':'Normal','params':spec['dist_params']},
                              'derive':spec['derive'], 'tol':tol, 'max_iter':max_iter})

    def test_convergence_before_cap_still_has_full_summary(self):
        payload = self._payload(tol=1e-8, max_iter=20)
        self.assertTrue(payload['flags']['converged'])
        self.assertGreater(len(payload['iterations']), 3)
        self.assertLess(len(payload['iterations']), 20)
        self.assertEqual([x['index'] for x in payload['steps_by_iteration']], [0, 1, 2])
        self.assertEqual([x['index'] for x in payload['iterations']],
                         list(range(len(payload['iterations']))))

    def test_fewer_than_three_iterations_only_expands_available(self):
        payload = self._payload(tol=0, max_iter=2)
        self.assertEqual(len(payload['iterations']), 2)
        self.assertEqual([x['index'] for x in payload['steps_by_iteration']], [0, 1])

    def test_terminal_prints_detailed_first_three_and_all_summary_rows(self):
        import re
        import subprocess
        import sys
        from pathlib import Path
        completed = subprocess.run([sys.executable, 'solve_steps.py', '-p', 'hw1',
                                    '--tol', '1e-8', '--max-iter', '20',
                                    '--no-pause', '--no-color'],
                                   capture_output=True, text=True,
                                   cwd=str(Path(__file__).resolve().parent),
                                   check=True)
        output = completed.stdout
        self.assertIn('Iteration 0   —', output)
        self.assertIn('Iteration 1   —', output)
        self.assertIn('Iteration 2   —', output)
        self.assertNotIn('Iteration 3   —', output)
        self.assertIn('Iterations 0 … 9, in brief', output)
        summary = output.split('Iterations 0 … 9, in brief',1)[1].split('Where it stopped',1)[0]
        displayed = re.findall(r'^\s+([0-9]+)\s+[0-9]+\.[0-9]{3}\s+', summary, re.M)
        self.assertEqual(displayed, [str(i) for i in range(10)])

    def test_excel_guide_omits_three_unwanted_rows_and_preserves_history(self):
        from excel_export import create_workbook
        from artifact_tool import SpreadsheetFile
        import tempfile
        from pathlib import Path
        payload=self._payload(tol=1e-8, max_iter=20)
        workbook=create_workbook(payload)
        guide=workbook.worksheets.get_item('Guide')
        headings=[row[0] for row in guide.get_range('A2:A12').values if row[0] is not None]
        for field in ('Converged','Note','Precision'):
            self.assertNotIn(field, headings)
        self.assertIn('Tolerance', headings)
        self.assertIn('Max iterations', headings)
        self.assertIn('Iterations', headings)
        history=workbook.worksheets.get_item('Iterations').get_range('A2:A11').values
        self.assertEqual([int(row[0]) for row in history], list(range(10)))
        self.assertEqual(len(payload['steps_by_iteration']),3)

    def test_excel_fallback_guide_has_no_warning_or_precision_rows(self):
        from excel_export import _stdlib_xlsx
        import io, zipfile, xml.etree.ElementTree as ET
        pkg=_stdlib_xlsx(self._payload(tol=1e-8,max_iter=20))
        with zipfile.ZipFile(io.BytesIO(pkg)) as book:
            xml=ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
        texts=[node.text for node in xml.iter() if node.text]
        for field in ('Converged','Note','Precision','Display'):
            self.assertNotIn(field,texts)


if __name__ == '__main__':
    unittest.main()


class GUIExcelSaveTests(unittest.TestCase):
    """The GUI must save the workbook inside run/, not start a browser download."""

    @staticmethod
    def _body(cap=8):
        s = list(EXAMPLES.values())[0]
        return {'D': s['D'], 'A': s['A'], 'h': s['h'], 'p': s['p'],
                'lead_time': 14, 'v': s['v'], 'base_unit': 'year',
                'lead_unit': 'week',
                'dist': {'name': 'Normal', 'params': s['dist_params']},
                'derive': s['derive'], 'max_iter': cap, 'tol': 0}

    @staticmethod
    def _post(url, data):
        import json
        import urllib.request
        payload = json.dumps(data).encode('utf-8')
        request = urllib.request.Request(url + '/api/export-xlsx',
                                         data=payload,
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=20) as resp:
            return resp.status, resp.headers.get('Content-Type'), json.load(resp)

    def test_output_is_always_inside_run_regardless_of_cwd(self):
        import webapp
        from pathlib import Path
        expected = Path(webapp.__file__).resolve().parent
        self.assertEqual(webapp.EXCEL_OUTPUT.parent, expected)
        self.assertEqual(webapp.EXCEL_OUTPUT.name, 'rq_iteration_results.xlsx')

    def test_http_export_saves_real_file_and_overwrites_with_latest_result(self):
        import tempfile
        import zipfile
        import xml.etree.ElementTree as ET
        from pathlib import Path
        from unittest.mock import patch
        import webapp
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'rq_iteration_results.xlsx'
            with patch.object(webapp, 'EXCEL_OUTPUT', target):
                server, thread, url = webapp.serve_in_background('127.0.0.1', 0)
                try:
                    self.assertFalse(target.exists())
                    status, typ, body = self._post(url, self._body(8))
                    self.assertEqual(status, 200)
                    self.assertIn('application/json', typ)
                    self.assertTrue(body['ok'])
                    self.assertEqual(body['saved_to'], str(target.resolve()))
                    self.assertTrue(target.is_file())
                    with zipfile.ZipFile(target) as z:
                        self.assertIn('xl/workbook.xml', z.namelist())
                        xml = ET.fromstring(z.read('xl/worksheets/sheet4.xml'))
                        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                        self.assertEqual(len(xml.findall(f'.//{ns}sheetData/{ns}row')), 9)
                    # Re-export a 3-iteration run: same path; content refreshed.
                    _, _, new_body = self._post(url, self._body(3))
                    self.assertEqual(new_body['saved_to'], body['saved_to'])
                    with zipfile.ZipFile(target) as z:
                        xml = ET.fromstring(z.read('xl/worksheets/sheet4.xml'))
                        self.assertEqual(len(xml.findall(f'.//{ns}sheetData/{ns}row')), 4)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)

    def test_error_does_not_claim_file_is_saved(self):
        import urllib.error
        from unittest.mock import patch
        import webapp
        with patch('excel_export.save_payload', side_effect=PermissionError('locked')):
            server, thread, url = webapp.serve_in_background('127.0.0.1', 0)
            try:
                with self.assertRaises(urllib.error.HTTPError) as err:
                    self._post(url, self._body(3))
                self.assertEqual(err.exception.code, 500)
                import json
                failure = json.loads(err.exception.read().decode('utf-8'))
                self.assertFalse(failure['ok'])
                self.assertIn('Close the Excel file', failure['error'])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
