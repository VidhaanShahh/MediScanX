"use client";

import { useEffect, useState, use } from "react";
import { api, CaseDetailResponse, AnalysisResponse, ReportResponse } from "@/lib/api";
import { formatDate, cn } from "@/lib/utils";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";

export default function CaseWorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const caseId = resolvedParams.id;
  const router = useRouter();
  
  const [caseDetail, setCaseDetail] = useState<CaseDetailResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // Upload state
  const [xrayFile, setXrayFile] = useState<File | null>(null);
  const [ecgFile, setEcgFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<"image" | "ecg" | null>(null);
  const [uploadMessage, setUploadMessage] = useState("");

  // Analysis state
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  // Report state
  const [generating, setGenerating] = useState(false);

  // View toggles
  const [showXrayGradCam, setShowXrayGradCam] = useState(false);
  const [showEcgSaliency, setShowEcgSaliency] = useState(false);

  useEffect(() => {
    fetchCase();
  }, [caseId]);

  const fetchCase = async () => {
    setIsLoading(true);
    try {
      const [cRes, rRes] = await Promise.all([
        api.get(`/api/cases/${caseId}`),
        api.get(`/api/reports/case/${caseId}`).catch(() => ({ data: [] }))
      ]);
      setCaseDetail(cRes.data);
      setReports(rRes.data);
    } catch (err) {
      console.error("Failed to load case", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpload = async (type: "image" | "ecg") => {
    const file = type === "image" ? xrayFile : ecgFile;
    if (!file) return;

    setUploading(type);
    setUploadMessage("");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await api.post(`/api/cases/${caseId}/upload`, formData, {
        params: { file_type: type },
        headers: { "Content-Type": "multipart/form-data" }
      });
      setUploadMessage(response.data.message || "Upload validated successfully.");
      if (type === "image") setXrayFile(null);
      if (type === "ecg") setEcgFile(null);
      await fetchCase();
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      const prefix = status ? `Upload failed (${status}). ` : "Upload failed. ";
      setUploadMessage(prefix + (detail || "Please check the file and try again."));
    } finally {
      setUploading(null);
    }
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setAnalysisError("");
    try {
      const res = await api.post(`/api/cases/${caseId}/analyze`);
      setAnalysis(res.data);
      await fetchCase();
    } catch (err: any) {
      setAnalysisError(err.response?.data?.detail || "Analysis failed due to a backend error.");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerateReport = async () => {
    setGenerating(true);
    try {
      await api.post(`/api/reports/cases/${caseId}/generate`);
      await fetchCase();
    } catch (err) {
      console.error("Failed to generate report", err);
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteCase = async () => {
    if (!window.confirm("Delete this case and its uploaded data, analysis, and reports? This action is permanent.")) return;
    try {
      await api.delete(`/api/cases/${caseId}`);
      router.push("/cases");
    } catch (err: any) {
      setAnalysisError(err.response?.data?.detail || "Case deletion failed.");
    }
  };

  const handleDownloadReport = async (reportId: string) => {
    try {
      const res = await api.get(`/api/reports/download/${reportId}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `report_${reportId}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error("Download failed", err);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900 dark:border-white"></div>
      </div>
    );
  }

  if (!caseDetail) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <div className="text-center p-8 bg-red-50 text-red-600 rounded-lg border border-red-100 max-w-md">
          <h2 className="text-xl font-bold mb-2">Workspace Not Found</h2>
          <p>The requested case could not be located in the system.</p>
        </div>
      </div>
    );
  }

  const isCompleted = caseDetail.status === "completed";
  const hasImage = caseDetail.imaging_studies?.length > 0;
  const hasEcg = caseDetail.ecg_records?.length > 0;
  const canAnalyze = hasImage || hasEcg;

  return (
    <div className="mx-auto max-w-7xl space-y-8 pb-16 font-sans">
      
      {/* 1. CASE HEADER */}
      <div className="border-b border-slate-200 pb-6 dark:border-slate-800">
        <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">
              <span>Cases</span><span>/</span><span>Workspace</span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">{caseDetail.name || "Name not recorded"}</h1>
              <span className={`inline-flex items-center gap-2 text-sm font-medium ${
                caseDetail.status === "completed" ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/50" :
                caseDetail.status === "error" ? "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800/50" :
                "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-900/20 dark:text-slate-400 dark:border-slate-800/50"
              }`}>
                <span className="h-2 w-2 rounded-full bg-current" aria-hidden="true" />
                {caseDetail.status}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm text-slate-600 dark:text-slate-400">
              <div className="flex items-center">
                <span className="text-slate-400 dark:text-slate-500 mr-2">Patient:</span> 
                <span className="font-medium text-slate-950 dark:text-white">{caseDetail.patient.full_name || "Name not recorded"}</span>
              </div>
              <div className="flex items-center">
                <span className="text-slate-400 dark:text-slate-500 mr-2">Created:</span> 
                {formatDate(caseDetail.created_at)}
              </div>
              <div className="flex items-center">
                <span className="text-slate-400 dark:text-slate-500 mr-2">Updated:</span> 
                {formatDate(caseDetail.updated_at)}
              </div>
            </div>
            <button onClick={handleDeleteCase} className="inline-flex items-center gap-2 self-start text-sm font-medium text-red-700 transition-colors hover:text-red-900 hover:underline dark:text-red-400 dark:hover:text-red-300">
              <Trash2 className="h-4 w-4" />
              Delete case
            </button>
          </div>
        </div>
      </div>

      {uploadMessage && (
        <div className="p-4 bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-800">
          <span className="font-medium">{uploadMessage}</span>
        </div>
      )}

      {analysisError && (
        <div className="p-4 bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-800">
          <span className="font-medium">Analysis Failed: {analysisError}</span>
        </div>
      )}

      {/* BEFORE ANALYSIS: UPLOAD & ACTION */}
      {(
        <>
        <div className="space-y-5">
          <div>
            <p className="text-xs font-medium text-teal-700 dark:text-teal-400">Input data</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">Upload modalities</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              
              {/* X-Ray Section */}
              <div className="border-y border-slate-200 py-5 dark:border-slate-800">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold text-slate-950 dark:text-white">
                    Chest X-Ray
                    </div>
                    <p className="mt-1 text-xs text-slate-500">JPEG, PNG, or DICOM</p>
                  </div>
                  {hasImage ? (
                    <span className="inline-flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-400"><span className="h-2 w-2 rounded-full bg-current" />Uploaded</span>
                  ) : (
                    <span className="inline-flex items-center gap-2 text-sm font-medium text-slate-500"><span className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />Not uploaded</span>
                  )}
                </div>
                
                <div className="flex flex-col justify-end">
                  {!hasImage && (
                    <>
                      <div className="relative mb-3 cursor-pointer rounded-md border border-dashed border-slate-300 p-4 text-center transition-colors hover:border-teal-600 hover:bg-teal-50/50 dark:border-slate-700 dark:hover:bg-teal-950/20">
                        <input 
                          type="file" 
                          accept="image/jpeg,image/png,image/dicom" 
                          onChange={(e) => setXrayFile(e.target.files?.[0] || null)}
                          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" 
                        />
                        <span className="text-sm text-slate-600 dark:text-slate-300">
                          {xrayFile ? xrayFile.name : "Select Image File"}
                        </span>
                      </div>
                      <button 
                        onClick={() => handleUpload("image")}
                        disabled={!xrayFile || uploading !== null}
                        className="w-full rounded-md bg-slate-900 py-2.5 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
                      >
                        {uploading === "image" ? "Uploading and validating..." : "Upload CXR"}
                      </button>
                    </>
                  )}
                  {hasImage && (
                    <p className="text-sm text-slate-600 dark:text-slate-400">Validated image available in this case.</p>
                  )}
                </div>
              </div>

              {/* ECG Section */}
              <div className="border-y border-slate-200 py-5 dark:border-slate-800">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold text-slate-950 dark:text-white">
                    12-Lead ECG
                    </div>
                    <p className="mt-1 text-xs text-slate-500">CSV, WFDB header, or data file</p>
                  </div>
                  {hasEcg ? (
                    <span className="inline-flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-400"><span className="h-2 w-2 rounded-full bg-current" />Uploaded</span>
                  ) : (
                    <span className="inline-flex items-center gap-2 text-sm font-medium text-slate-500"><span className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />Not uploaded</span>
                  )}
                </div>
                
                <div className="flex flex-col justify-end">
                  {!hasEcg && (
                    <>
                      <div className="relative mb-3 cursor-pointer rounded-md border border-dashed border-slate-300 p-4 text-center transition-colors hover:border-teal-600 hover:bg-teal-50/50 dark:border-slate-700 dark:hover:bg-teal-950/20">
                        <input 
                          type="file" 
                          accept=".csv,.hea,.dat" 
                          onChange={(e) => setEcgFile(e.target.files?.[0] || null)}
                          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" 
                        />
                        <span className="text-sm text-slate-600 dark:text-slate-300">
                          {ecgFile ? ecgFile.name : "Select Signal File"}
                        </span>
                      </div>
                      <button 
                        onClick={() => handleUpload("ecg")}
                        disabled={!ecgFile || uploading !== null}
                        className="w-full rounded-md bg-slate-900 py-2.5 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
                      >
                        {uploading === "ecg" ? "Uploading and validating..." : "Upload ECG"}
                      </button>
                    </>
                  )}
                  {hasEcg && (
                    <p className="text-sm text-slate-600 dark:text-slate-400">Validated waveform available in this case.</p>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="border-y border-slate-200 py-5 dark:border-slate-800">
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Analysis</h2>
            <div className="mt-3 max-w-2xl">
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Run available AI models based on uploaded modalities.
                </p>
                <button
                  onClick={handleAnalyze}
                  disabled={analyzing || !canAnalyze}
                  className="mt-4 rounded-md bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
                >
                  {analyzing ? "Processing..." : "Start Analysis"}
                </button>
                {!canAnalyze && (
                  <p className="mt-3 text-xs text-slate-500">
                    Upload at least one modality to proceed.
                  </p>
                )}
            </div>
          </div>
        </>
      )}

      {/* AFTER ANALYSIS: RESULTS */}
      {isCompleted && analysis && (
        <div className="space-y-10 border-t border-slate-200 pt-8 dark:border-slate-800">
          
          {/* 5. MULTIMODAL SUMMARY */}
          {analysis.fusion && (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-medium text-teal-700 dark:text-teal-400">Analysis summary</p>
                <h2 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">Multimodal analysis</h2>
              </div>
              <div className="grid grid-cols-2 divide-x divide-slate-200 border-y border-slate-200 py-4 dark:divide-slate-800 dark:border-slate-800 lg:grid-cols-4">
                
                <div className="px-4 first:pl-0">
                  <p className="text-xs font-medium text-slate-500">Image screening</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">
                    {analysis.fusion.image_score != null ? analysis.fusion.image_score.toFixed(3) : "N/A"}
                  </p>
                </div>
                
                <div className="px-4">
                  <p className="text-xs font-medium text-slate-500">ECG screening</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">
                    {analysis.fusion.ecg_score != null ? analysis.fusion.ecg_score.toFixed(3) : "N/A"}
                  </p>
                </div>

                <div className="px-4">
                  <p className="text-xs font-medium text-slate-500">Multimodal fusion</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">
                    {analysis.fusion.fusion_score.toFixed(3)}
                  </p>
                </div>

                <div className="px-4 pr-0">
                  <p className="text-xs font-medium text-slate-500">Risk band</p>
                  <p className={`mt-1 text-2xl font-semibold ${
                    analysis.fusion.risk_band === 'high' ? 'text-red-600 dark:text-red-400' :
                    analysis.fusion.risk_band === 'moderate' ? 'text-amber-600 dark:text-amber-400' :
                    'text-emerald-600 dark:text-emerald-400'
                  }`}>
                    {analysis.fusion.risk_band.toUpperCase()}
                  </p>
                </div>
                
              </div>
              
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
                <span>Modality used: <strong className="font-medium text-slate-800 dark:text-slate-200">{analysis.fusion.modality_used}</strong>
                </span>
                <span>Disagreement: <strong className="font-medium text-slate-800 dark:text-slate-200">{analysis.fusion.disagreement ? "Yes" : "No"}</strong>
                </span>
                {analysis.fusion.difference != null && (
                  <span>Difference: <strong className="font-medium text-slate-800 dark:text-slate-200">{analysis.fusion.difference.toFixed(3)}</strong>
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 7 & 8. CHEST X-RAY WORKSPACE */}
          {hasImage && (
            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                  X-ray findings
                </h2>
                {analysis.imaging_predictions && (
                  <div className="text-right">
                    <p className="text-xs text-slate-500 uppercase tracking-wide">Model Output</p>
                    <p className="text-sm font-mono text-slate-700 dark:text-slate-300">{analysis.imaging_predictions.model_name} {analysis.imaging_predictions.model_version}</p>
                  </div>
                )}
              </div>
              
              <div className="border-y border-slate-200 py-5 dark:border-slate-800">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  {/* Image Viewer */}
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <h3 className="text-sm font-medium text-slate-800 dark:text-slate-200">Explainability</h3>
                      <div className="flex bg-slate-100 dark:bg-slate-800 p-1 rounded">
                        <button 
                          onClick={() => setShowXrayGradCam(false)}
                          className={cn("px-3 py-1 text-xs font-medium rounded transition-colors", !showXrayGradCam ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300")}
                        >
                          Original
                        </button>
                        <button 
                          onClick={() => setShowXrayGradCam(true)}
                          className={cn("px-3 py-1 text-xs font-medium rounded transition-colors", showXrayGradCam ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300")}
                        >
                          Grad-CAM
                        </button>
                      </div>
                    </div>
                    
                    <div className="aspect-[4/3] overflow-hidden rounded-md border border-slate-200 bg-slate-950 dark:border-slate-700">
                      {!showXrayGradCam && (
                        <img 
                          src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/${caseDetail.imaging_studies[0].file_path}`} 
                          alt="Original Chest X-Ray"
                          className="object-contain w-full h-full"
                        />
                      )}
                      {showXrayGradCam && analysis.explanations?.find(e => e.modality === 'imaging') ? (
                        <img 
                          src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/${analysis.explanations.find(e => e.modality === 'imaging')?.file_path}`} 
                          alt="Grad-CAM Visualization"
                          className="object-contain w-full h-full"
                        />
                      ) : showXrayGradCam && (
                        <p className="text-slate-500 font-medium text-sm">Grad-CAM not available</p>
                      )}
                    </div>
                  </div>
                  
                  {/* 14 Classes Output */}
                  <div className="overflow-x-auto">
                    <h3 className="mb-3 text-sm font-medium text-slate-800 dark:text-slate-200">Findings</h3>
                    <table className="w-full text-left text-sm">
                      <thead className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800"><tr><th className="py-2 font-medium">Condition</th><th className="py-2 text-right font-medium">Probability</th><th className="py-2 text-right font-medium">Status</th></tr></thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {analysis.imaging_predictions?.predictions.map((p, i) => (
                        <tr key={i}><td className="py-2 capitalize text-slate-700 dark:text-slate-300">{p.disease.replace('_', ' ')}</td><td className="py-2 text-right font-mono text-slate-700 dark:text-slate-300">{(p.probability * 100).toFixed(1)}%</td><td className="py-2 text-right text-xs text-slate-500">{p.probability >= 0.5 ? "Above threshold" : "Below threshold"}</td></tr>
                      ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 9 & 10. ECG WORKSPACE */}
          {hasEcg && (
            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                  ECG findings
                </h2>
                {analysis.ecg_predictions && (
                  <div className="text-right">
                    <p className="text-xs text-slate-500 uppercase tracking-wide">Model Output</p>
                    <p className="text-sm font-mono text-slate-700 dark:text-slate-300">{analysis.ecg_predictions.model_name} {analysis.ecg_predictions.model_version}</p>
                  </div>
                )}
              </div>
              
              <div className="border-y border-slate-200 py-5 dark:border-slate-800">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  {/* Image Viewer */}
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <h3 className="text-sm font-medium text-slate-800 dark:text-slate-200">Explainability</h3>
                      <div className="flex bg-slate-100 dark:bg-slate-800 p-1 rounded">
                        <button 
                          onClick={() => setShowEcgSaliency(false)}
                          className={cn("px-3 py-1 text-xs font-medium rounded transition-colors", !showEcgSaliency ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300")}
                        >
                          Waveform
                        </button>
                        <button 
                          onClick={() => setShowEcgSaliency(true)}
                          className={cn("px-3 py-1 text-xs font-medium rounded transition-colors", showEcgSaliency ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300")}
                        >
                          Saliency
                        </button>
                      </div>
                    </div>
                    
                    <div className="aspect-[4/3] overflow-hidden rounded-md border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-800">
                      {!showEcgSaliency && analysis.ecg_predictions?.plot_image_base64 ? (
                        <img 
                          src={`data:image/png;base64,${analysis.ecg_predictions.plot_image_base64}`} 
                          alt="12-Lead ECG Waveform"
                          className="object-contain w-full h-full"
                        />
                      ) : !showEcgSaliency ? (
                        <p className="text-slate-500 font-medium text-sm">Waveform render not available</p>
                      ) : null}

                      {showEcgSaliency && analysis.explanations?.find(e => e.modality === 'ecg') ? (
                        <img 
                          src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/${analysis.explanations.find(e => e.modality === 'ecg')?.file_path}`} 
                          alt="ECG Saliency Visualization"
                          className="object-contain w-full h-full"
                        />
                      ) : showEcgSaliency && (
                        <p className="text-slate-500 font-medium text-sm">ECG saliency visualization not available for this analysis.</p>
                      )}
                    </div>
                  </div>
                  
                  {/* 5 Classes Output & HR */}
                  <div className="overflow-x-auto">
                    {analysis.ecg_predictions?.heart_rate_bpm && (
                      <div className="mb-6 p-4 bg-slate-50 dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-800 flex justify-between items-center">
                        <span className="font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide text-xs">Estimated Heart Rate</span>
                        <span className="text-xl font-bold text-slate-900 dark:text-white">{analysis.ecg_predictions.heart_rate_bpm} <span className="text-xs font-medium text-slate-500">BPM</span></span>
                      </div>
                    )}

                    <h3 className="mb-3 text-sm font-medium text-slate-800 dark:text-slate-200">Findings</h3>
                    <table className="w-full text-left text-sm"><thead className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800"><tr><th className="py-2 font-medium">Finding</th><th className="py-2 text-right font-medium">Probability</th><th className="py-2 text-right font-medium">Threshold</th></tr></thead><tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {analysis.ecg_predictions?.predictions.map((p, i) => (
                        <tr key={i}><td className="py-2 text-slate-700 dark:text-slate-300">{p.superclass.replace('_', ' ')}</td><td className="py-2 text-right font-mono text-slate-700 dark:text-slate-300">{(p.probability * 100).toFixed(1)}%</td><td className="py-2 text-right text-xs text-slate-500">{(p.threshold * 100).toFixed(1)}% · {p.above_threshold ? "Above" : "Below"}</td></tr>
                      ))}
                    </tbody></table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 11. EXPLAINABILITY DISCLAIMER */}
          <div className="border-y border-slate-200 py-5 dark:border-slate-800">
            <h2 className="mb-2 text-sm font-semibold text-slate-950 dark:text-white">
              Explainability
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
              Visualization of model-associated regions/signal segments. Interpretability aid only; not evidence of causality.
              Inference Time: {(analysis.imaging_predictions?.inference_ms || 0) + (analysis.ecg_predictions?.inference_ms || 0)}ms total.
            </p>
          </div>

          {/* 18. REPORTING */}
          <div className="border-y border-slate-200 py-5 dark:border-slate-800">
            <div className="mb-5 flex flex-col items-start justify-between gap-4 md:flex-row md:items-center">
              <div>
                 <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                   Report
                </h2>
              </div>
              <button
                onClick={handleGenerateReport}
                disabled={generating}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
              >
                {generating ? "Generating..." : "Generate Report"}
              </button>
            </div>

            {reports.length > 0 ? (
                <div className="overflow-x-auto border-y border-slate-200 dark:border-slate-800">
                <table className="w-full text-sm text-left">
                  <thead className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">Report ID</th>
                      <th className="px-6 py-4 font-medium">Generated At</th>
                      <th className="px-6 py-4 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                    {reports.map((report) => (
                      <tr key={report.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                        <td className="px-6 py-4 font-mono text-slate-700 dark:text-slate-300">{report.id}</td>
                        <td className="px-6 py-4 text-slate-600 dark:text-slate-400">{formatDate(report.generated_at)}</td>
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => handleDownloadReport(report.id)}
                            className="text-slate-900 dark:text-white font-medium hover:underline text-xs uppercase tracking-wide"
                          >
                            Download
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-8 text-center text-sm text-slate-500">
                No reports generated yet.
              </div>
            )}
          </div>
          
        </div>
      )}
    </div>
  );
}
