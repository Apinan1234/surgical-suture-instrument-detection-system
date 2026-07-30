import { useState, FormEvent } from 'react';
import { Header } from './components/Header';
import { Hero } from './components/Hero';
import { Cards } from './components/Cards';
import { FeatureGridSection } from './components/FeatureGridSection';
import { ScrollAnimation } from './components/ScrollAnimation';
import { X, CheckCircle, ArrowRight, Eye } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('Overview');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [email, setEmail] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (email) {
      setSubmitted(true);
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSubmitted(false);
    setEmail('');
  };

  return (
    <div className="min-h-screen text-white font-['DM_Sans'] antialiased flex flex-col items-center justify-start p-2 sm:p-4 pb-12 selection:bg-white selection:text-black">
      <ScrollAnimation />
      {/* Container Banner Section */}
      <div className="w-full max-w-7xl min-h-[900px] bg-transparent border-transparent rounded-3xl flex flex-col justify-between p-4 sm:p-6 lg:p-8 relative overflow-hidden shadow-2xl my-auto">
        {/* Top Banner Navigation */}
        <Header activeTab={activeTab} setActiveTab={setActiveTab} />

        {/* Main Banner Content */}
        <div className="flex-1 flex flex-col justify-center my-auto py-4">
          <Hero onCtaClick={() => setIsModalOpen(true)} />
          <Cards />
        </div>

        {/* Footer copyright note */}
        <footer className="w-full text-center text-xs text-white/40 pt-2 font-['DM_Sans']">
          © AI Surgical Instrument Detection System. Built for real-time surgical support & veterinary training.
        </footer>
      </div>

      {/* Second Section - 4 Cards Layout with Empty Center Space */}
      <FeatureGridSection />

      {/* Research Modal Dialogue */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fadeIn">
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-black/60 backdrop-blur-xl border border-white/20 rounded-3xl p-6 sm:p-8 shadow-2xl text-white font-['DM_Sans']">
            <button
              onClick={closeModal}
              className="absolute top-5 right-5 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors cursor-pointer"
              aria-label="Close modal"
            >
              <X size={20} />
            </button>

            {!submitted ? (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-widest text-[#0066FF] bg-[#0066FF]/10 px-3 py-1 rounded-full border border-[#0066FF]/20">
                    Phase 1 Research Brief
                  </span>
                </div>
                <h3 className="text-2xl sm:text-3xl font-medium text-white mb-2">
                  AI Surgical Instrument Detection
                </h3>
                <p className="text-white/80 text-sm mb-6">
                  Key benchmarks and architecture details from our YOLOv11 real-time veterinary suturing model.
                </p>

                {/* Key Metrics Grid */}
                <div className="grid grid-cols-3 gap-3 mb-6">
                  <div className="bg-white/5 border border-white/10 rounded-xl p-3 text-center">
                    <div className="text-xl sm:text-2xl font-bold text-white">68.1%</div>
                    <div className="text-[11px] text-white/60 uppercase tracking-wider font-medium mt-0.5">mAP@50</div>
                  </div>
                  <div className="bg-white/5 border border-white/10 rounded-xl p-3 text-center">
                    <div className="text-xl sm:text-2xl font-bold text-white">80.5%</div>
                    <div className="text-[11px] text-white/60 uppercase tracking-wider font-medium mt-0.5">Precision</div>
                  </div>
                  <div className="bg-white/5 border border-white/10 rounded-xl p-3 text-center">
                    <div className="text-xl sm:text-2xl font-bold text-white">73.1%</div>
                    <div className="text-[11px] text-white/60 uppercase tracking-wider font-medium mt-0.5">Recall</div>
                  </div>
                </div>

                {/* Detected Classes */}
                <div className="bg-white/5 border border-white/10 rounded-2xl p-4 mb-6">
                  <h4 className="text-xs font-medium text-white/80 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                    <Eye size={14} className="text-[#0066FF]" /> 5 Key Procedure Elements Detected
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {['Needle', "Operator's Hand", 'Needle Holder', 'Wound Area', 'Forceps'].map((tag, i) => (
                      <span key={i} className="text-xs bg-white/10 border border-white/15 px-3 py-1 rounded-full text-white">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Form to Request Full Whitepaper */}
                <form onSubmit={handleSubmit} className="space-y-4 border-t border-white/10 pt-5">
                  <div>
                    <label className="block text-xs font-medium text-white/80 uppercase tracking-wider mb-1.5">
                      Request Complete Dataset & Paper
                    </label>
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="researcher@university.edu"
                      className="w-full bg-white/5 border border-white/20 rounded-xl px-4 py-3 text-white placeholder-white/40 focus:outline-none focus:border-white transition-colors text-sm"
                    />
                  </div>

                  <button
                    type="submit"
                    className="w-full bg-white text-black font-medium py-3 px-6 rounded-xl hover:bg-white/90 transition-all flex items-center justify-center gap-2 text-sm font-['DM_Sans'] cursor-pointer"
                  >
                    <span>Request Research Paper PDF</span>
                    <ArrowRight size={18} />
                  </button>
                </form>
              </div>
            ) : (
              <div className="text-center py-6">
                <CheckCircle className="w-12 h-12 text-[#0066FF] mx-auto mb-4" />
                <h3 className="text-2xl font-medium text-white mb-2">
                  Research PDF Sent
                </h3>
                <p className="text-white/80 text-sm mb-6">
                  Thank you! The Phase 1 research paper and model architecture summary have been dispatched to <span className="text-white font-medium">{email}</span>.
                </p>
                <button
                  onClick={closeModal}
                  className="bg-white text-black font-medium px-6 py-2.5 rounded-full text-sm hover:bg-white/90 transition-all cursor-pointer font-['DM_Sans']"
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

