import { ArrowUpRight } from 'lucide-react';
import { motion } from 'motion/react';

interface HeroProps {
  onCtaClick?: () => void;
}

export function Hero({ onCtaClick }: HeroProps) {
  return (
    <section className="relative z-10 text-center px-4 sm:px-6 lg:px-8 pt-10 sm:pt-16 pb-4 sm:pb-6 flex flex-col items-center justify-center mx-auto w-full max-w-md">
      {/* Main Headline - forced to 3 lines */}
      <motion.h1 
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="text-3xl sm:text-[54px] font-medium tracking-tight text-white leading-[1.12] mx-auto font-['DM_Sans']"
      >
        See Every Suture.<br />
        Understand<br />
        Every Step.
      </motion.h1>

      {/* Subheadline */}
      <motion.p 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
        className="mt-3 text-sm sm:text-base text-white/90 font-normal mx-auto leading-relaxed font-['DM_Sans']"
      >
        An AI-powered vision system that detects surgical instruments and wound areas in real time — built to support veterinary training, procedure analysis, and the future of surgical decision-support.
      </motion.p>

      {/* CTA Button */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut", delay: 0.4 }}
        className="mt-4"
      >
        <button
          onClick={onCtaClick}
          className="group inline-flex items-center bg-white text-black pl-6 pr-1.5 py-1.5 rounded-full font-medium shadow-xl hover:bg-white/95 transition-all duration-300 cursor-pointer border border-white"
        >
          <span className="text-sm font-medium font-['DM_Sans'] text-black tracking-tight">
            View the Research
          </span>
          <div className="w-8 h-8 ml-3 rounded-full bg-[#0066FF] flex items-center justify-center text-white group-hover:scale-105 group-hover:bg-[#0052cc] transition-all duration-300">
            <ArrowUpRight className="w-4 h-4 stroke-[2.5]" />
          </div>
        </button>
      </motion.div>
    </section>
  );
}


