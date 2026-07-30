import { Eye, Cpu, Activity, ShieldCheck } from 'lucide-react';
import { motion } from 'motion/react';

export function FeatureGridSection() {
  const leftCards = [
    {
      title: "Real-time Segmentation",
      icon: Eye,
      content: "High-precision boundary detection tracking delicate surgical field landmarks and tissue margins frame by frame."
    },
    {
      title: "Frame-by-Frame Tracking",
      icon: Cpu,
      content: "Deep learning trajectory tracing for suture needles and instrument tips with sub-millisecond motion analysis."
    }
  ];

  const rightCards = [
    {
      title: "Automated Analytics",
      icon: Activity,
      content: "Continuous operational telemetry generating actionable metrics on technique, duration, and procedural flow."
    },
    {
      title: "In-Theater Decision Support",
      icon: ShieldCheck,
      content: "Context-aware intelligence assisting surgical teams with real-time feedback and procedural compliance verification."
    }
  ];

  return (
    <section className="w-full max-w-7xl mx-auto mt-8 relative">
      {/* Black Container Box matching other sections */}
      <div className="w-full bg-transparent border-transparent rounded-3xl p-6 sm:p-8 md:p-10 relative overflow-hidden shadow-2xl text-white font-['DM_Sans']">
        
        {/* Section Header */}
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="text-center max-w-2xl mx-auto mb-8 sm:mb-12"
        >
          <h2 className="text-2xl sm:text-4xl font-medium tracking-tight text-white mb-3">
            Core Technical Architecture
          </h2>
          <p className="text-xs sm:text-sm text-white/70 font-normal">
            Modular visual intelligence modules engineered for high-frequency surgical environment analysis.
          </p>
        </motion.div>

        {/* 3-Column Split Layout: 2 Left Cards, Center Empty Space, 2 Right Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
          
          {/* Left Side: 2 Cards */}
          <motion.div 
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
            className="lg:col-span-4 flex flex-col gap-5 justify-between"
          >
            {leftCards.map((card, idx) => {
              const Icon = card.icon;
              return (
                <div
                  key={idx}
                  className="bg-white/10 border border-white/15 backdrop-blur-md rounded-2xl p-5 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 flex-1"
                >
                  <div>
                    <div className="bg-white p-2 rounded-lg w-9 h-9 flex items-center justify-center mb-3 shadow-md">
                      <Icon className="w-4 h-4 text-[#0066FF]" />
                    </div>

                    <h3 className="text-base sm:text-lg font-medium text-white mb-2 tracking-tight font-['DM_Sans']">
                      {card.title}
                    </h3>

                    <p className="text-white/90 text-xs sm:text-sm leading-relaxed font-['DM_Sans'] font-normal">
                      {card.content}
                    </p>
                  </div>
                </div>
              );
            })}
          </motion.div>

          {/* Center Column: Empty Space (Reserved for future visuals) */}
          <div className="lg:col-span-4 min-h-[240px] lg:min-h-[420px] rounded-2xl flex items-center justify-center">
            {/* Kept entirely empty as requested */}
          </div>

          {/* Right Side: 2 Cards */}
          <motion.div 
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.4 }}
            className="lg:col-span-4 flex flex-col gap-5 justify-between"
          >
            {rightCards.map((card, idx) => {
              const Icon = card.icon;
              return (
                <div
                  key={idx}
                  className="bg-white/10 border border-white/15 backdrop-blur-md rounded-2xl p-5 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 flex-1"
                >
                  <div>
                    <div className="bg-white p-2 rounded-lg w-9 h-9 flex items-center justify-center mb-3 shadow-md">
                      <Icon className="w-4 h-4 text-[#0066FF]" />
                    </div>

                    <h3 className="text-base sm:text-lg font-medium text-white mb-2 tracking-tight font-['DM_Sans']">
                      {card.title}
                    </h3>

                    <p className="text-white/90 text-xs sm:text-sm leading-relaxed font-['DM_Sans'] font-normal">
                      {card.content}
                    </p>
                  </div>
                </div>
              );
            })}
          </motion.div>

        </div>

      </div>
    </section>
  );
}
