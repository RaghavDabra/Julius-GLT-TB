import React, { useState } from 'react';
import {
  FileUp as FileUpload,
  Settings,
  MessageSquare,
} from 'lucide-react';
import FinancialDataUpload from './FinancialDataUpload';
import FinancialReconciliation from './FinancialReconciliation';
import LLMChat from './LLMChat';
import AuditTrail from './AuditTrail';
import { cn } from '../lib/Utils';

const steps = [
  { id: 'upload', title: 'Upload GL & TB', icon: FileUpload },
  { id: 'reconcile', title: 'Reconcile', icon: Settings },
  { id: 'chat', title: 'Insights', icon: MessageSquare },
  { id: 'audit', title: 'Audit Trail', icon: Settings },
];

const Dashboard: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0);
  const [glFile, setGlFile] = useState<File | null>(null);
  const [tbFile, setTbFile] = useState<File | null>(null);
  const [processedSummary, setProcessedSummary] = useState<string>('');
  const [runId, setRunId] = useState<string>('');

  // If you still want to control navigation programmatically:
  const handleNext = () => setActiveStep((prev) => prev + 1);

  const renderStepContent = (step: number) => {
    switch (step) {
      case 0:
        return (
          <FinancialDataUpload
            onComplete={({ glFile: nextGl, tbFile: nextTb }) => {
              setGlFile(nextGl);
              setTbFile(nextTb);
              handleNext();
            }}
          />
        );
      case 1:
        if (!glFile || !tbFile) return <div>Missing files</div>;
        return (
          <FinancialReconciliation
            glFile={glFile}
            tbFile={tbFile}
            onComplete={({ runId: nextRunId, processedSummary: nextSummary }) => {
              setRunId(nextRunId);
              setProcessedSummary(nextSummary);
              handleNext();
            }}
          />
        );
      case 2:
        return <LLMChat processedSummary={processedSummary} runId={runId} />;
      case 3:
        if (!runId) return <div>No run yet</div>;
        return <AuditTrail runId={runId} />;
      default:
        return <div>Unknown Step</div>;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* Navigation bar */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div />
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-center">
            <nav aria-label="Progress" className="w-full">
              <ol className="flex items-center justify-between w-full">
                {steps.map((step, index) => (
                  <li
                    key={step.id}
                    className={cn(
                      'relative flex items-center',
                      index !== steps.length - 1 && 'flex-1'
                    )}
                  >
                    <div className="flex items-center justify-center">
                      <button
                        className={cn(
                          'h-12 w-12 rounded-full flex items-center justify-center transition-colors duration-200 ease-in-out',
                          index <= activeStep
                            ? 'bg-green-600 hover:bg-green-700'
                            : 'bg-green-200'
                        )}
                        onClick={() => setActiveStep(index)}
                      >
                        <step.icon
                          className={cn(
                            'w-6 h-6',
                            index <= activeStep ? 'text-white' : 'text-green-600'
                          )}
                        />
                      </button>
                      <span className="absolute -bottom-6 w-max text-sm font-medium text-gray-900">
                        {step.title}
                      </span>
                    </div>
                    {index !== steps.length - 1 && (
                      <div
                        className={cn(
                          'flex-1 h-0.5 mx-4',
                          index < activeStep ? 'bg-green-600' : 'bg-green-200'
                        )}
                      />
                    )}
                  </li>
                ))}
              </ol>
            </nav>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-6">
          {renderStepContent(activeStep)}
        </div>

        {/* 
          Back and Next buttons removed.
          If you only want to navigate by clicking the steps above,
          you can leave the handleNext/handleBack logic in place or remove it entirely.
        */}
      </main>

    </div>
  );
};

export default Dashboard;
