"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { api, CaseResponse, PatientResponse } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function PatientDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [patient, setPatient] = useState<PatientResponse | null>(null);
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [caseName, setCaseName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [patientResponse, casesResponse] = await Promise.all([
          api.get(`/api/patients/${id}`),
          api.get(`/api/patients/${id}/cases`),
        ]);
        setPatient(patientResponse.data);
        setCases(casesResponse.data);
      } catch (err: any) {
        setError(err.response?.data?.detail || "Unable to load patient.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const createCase = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await api.post("/api/cases", { patient_id: id, name: caseName.trim() });
      router.push(`/cases/${response.data.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Unable to create case.");
      setSaving(false);
    }
  };

  const deletePatient = async () => {
    if (!window.confirm("Delete this patient and all associated cases, uploads, analysis, and reports? This action is permanent.")) return;
    try {
      await api.delete(`/api/patients/${id}`);
      router.push("/patients");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Patient deletion failed.");
    }
  };

  if (loading) return <div className="text-sm text-slate-500">Loading patient record...</div>;
  if (!patient) return <div className="text-sm text-red-700">{error || "Patient not found."}</div>;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex items-center gap-4">
        <Link href="/patients" className="rounded-md p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-white" aria-label="Back to patients">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <p className="text-sm text-slate-500">Patient record</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">{patient.full_name || "Unnamed patient"}</h1>
        </div>
        <button onClick={deletePatient} className="inline-flex items-center gap-2 rounded-md border border-red-200 px-3 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-900/50 dark:text-red-400 dark:hover:bg-red-950/30">
          <Trash2 className="h-4 w-4" /> Delete patient
        </button>
      </div>

      {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-300">{error}</div>}

      <section className="grid gap-4 border-y border-slate-200 py-6 sm:grid-cols-4 dark:border-slate-800">
        <div><p className="text-xs text-slate-500">Anonymous ID</p><p className="mt-1 font-mono text-sm text-slate-900 dark:text-white">{patient.anon_code}</p></div>
        <div><p className="text-xs text-slate-500">Age</p><p className="mt-1 text-sm text-slate-900 dark:text-white">{patient.age ?? "Not recorded"}</p></div>
        <div><p className="text-xs text-slate-500">Sex</p><p className="mt-1 text-sm text-slate-900 dark:text-white">{patient.sex || "Not recorded"}</p></div>
        <div><p className="text-xs text-slate-500">Created</p><p className="mt-1 text-sm text-slate-900 dark:text-white">{formatDate(patient.created_at)}</p></div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div><h2 className="text-lg font-semibold text-slate-950 dark:text-white">Cases</h2><p className="text-sm text-slate-500">Screening workspaces linked to this patient.</p></div>
          <button onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"><Plus className="h-4 w-4" /> New case</button>
        </div>
        <div className="overflow-x-auto border-y border-slate-200 dark:border-slate-800">
          <table className="w-full text-left text-sm"><thead className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800"><tr><th className="px-3 py-3 font-medium">Case</th><th className="px-3 py-3 font-medium">Status</th><th className="px-3 py-3 font-medium">Created</th><th className="px-3 py-3 text-right font-medium">Action</th></tr></thead><tbody className="divide-y divide-slate-100 dark:divide-slate-800">{cases.map((item) => <tr key={item.id}><td className="px-3 py-4 font-medium text-slate-900 dark:text-white">{item.name || "Unnamed case"}</td><td className="px-3 py-4 text-slate-600 dark:text-slate-300">{item.status}</td><td className="px-3 py-4 text-slate-500">{formatDate(item.created_at)}</td><td className="px-3 py-4 text-right"><Link href={`/cases/${item.id}`} className="font-medium text-slate-900 hover:underline dark:text-white">Open</Link></td></tr>)}</tbody></table>
          {cases.length === 0 && <p className="px-3 py-8 text-sm text-slate-500">No cases yet. Create a case to begin screening.</p>}
        </div>
      </section>

      {showCreate && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="new-case-title"><form onSubmit={createCase} className="w-full max-w-md space-y-5 rounded-lg border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-700 dark:bg-slate-900"><h2 id="new-case-title" className="text-lg font-semibold text-slate-950 dark:text-white">Create case</h2><div><label htmlFor="case-name" className="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-300">Case name</label><input id="case-name" required maxLength={255} value={caseName} onChange={(event) => setCaseName(event.target.value)} className="w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:border-slate-600 dark:border-slate-700 dark:text-white" placeholder="Initial screening" /></div><div className="flex justify-end gap-3"><button type="button" onClick={() => setShowCreate(false)} className="rounded-md px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">Cancel</button><button type="submit" disabled={saving} className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-slate-900">{saving ? "Creating..." : "Create case"}</button></div></form></div>}
    </div>
  );
}
