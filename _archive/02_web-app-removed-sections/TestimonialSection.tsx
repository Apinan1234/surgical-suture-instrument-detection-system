import { useState } from 'react';
import { ChevronLeft, ChevronRight, Quote } from 'lucide-react';
import { motion } from 'motion/react';

const berniceImg = '/src/assets/images/bernice_portrait_1785374374738.jpg';
const davidImg = '/src/assets/images/david_portrait_1785374388164.jpg';
const elenaImg = '/src/assets/images/elena_portrait_1785374400409.jpg';

export function TestimonialSection() {
  const [activeIndex, setActiveIndex] = useState(0);

  const testimonials = [
    {
      id: 1,
      image: berniceImg,
      name: "BERNICE TAY",
      title: "Bright Culture",
      quote: "« I WASTED MY TIME WITH OTHER AGENCIES, BUT WITH OMNI, WE INCREASED OUR REVENUE AND GOT MORE STUDENTS WITH LOW CPL AND HIGH ROAS »",
      stats: [
        { value: "$15–25", label: "CPL" },
        { value: "263", label: "Webinar attendees" },
        { value: "11.11X", label: "ROAS for Crash Course" }
      ]
    },
    {
      id: 2,
      image: davidImg,
      name: "DR. DAVID CHEN",
      title: "Lead Surgical Instructor, VetMed",
      quote: "« INTEGRATING THE YOLOV11 SURGICAL DETECTION PIPELINE CUT OUR INSTRUMENT IDENTIFICATION ERROR BY 74% DURING COMPLEX SUTURING TRIALS »",
      stats: [
        { value: "74%", label: "Error Reduction" },
        { value: "120+", label: "Annotated Sequences" },
        { value: "68.1%", label: "mAP@50 Benchmark" }
      ]
    },
    {
      id: 3,
      image: elenaImg,
      name: "DR. ELENA RODRIGUEZ",
      title: "Director, AI Vision Lab",
      quote: "« REAL-TIME FEEDBACK DURING ANIMAL SUTURING PROCEDURES DRAMATICALLY SPEED UP STUDENT CONFIDENCE AND PRECISION REPEATABILITY »",
      stats: [
        { value: "80.5%", label: "Model Precision" },
        { value: "73.1%", label: "Recall Rate" },
        { value: "< 18ms", label: "Real-time Latency" }
      ]
    }
  ];

  const current = testimonials[activeIndex];

  const handleNext = () => {
    setActiveIndex((prev) => (prev + 1) % testimonials.length);
  };

  const handlePrev = () => {
    setActiveIndex((prev) => (prev - 1 + testimonials.length) % testimonials.length);
  };

  return (
    <section className="w-full max-w-7xl mx-auto mt-8 relative">
      {/* Black Container matching main sections */}
      <div className="w-full bg-transparent border-transparent rounded-3xl p-6 sm:p-8 md:p-10 relative overflow-hidden shadow-2xl text-white font-['DM_Sans']">
        
        {/* Top Header / Carousel Controls */}
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 sm:mb-8 border-b border-white/10 pb-5"
        >
          <div>
            <div className="text-xs font-semibold uppercase tracking-widest text-[#0066FF] mb-1">
              Impact & Results
            </div>
            <h2 className="text-xl sm:text-2xl font-medium text-white tracking-tight">
              What Our Partners & Researchers Say
            </h2>
          </div>

          {/* Selector Tabs & Navigation Buttons */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full p-1">
              {testimonials.map((t, idx) => (
                <button
                  key={t.id}
                  onClick={() => setActiveIndex(idx)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-all cursor-pointer ${
                    activeIndex === idx
                      ? 'bg-white text-black font-semibold shadow-md'
                      : 'text-white/60 hover:text-white hover:bg-white/10'
                  }`}
                >
                  0{idx + 1}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={handlePrev}
                aria-label="Previous Testimonial"
                className="w-8 h-8 rounded-full border border-white/15 bg-white/5 hover:bg-white/15 flex items-center justify-center text-white transition-colors cursor-pointer"
              >
                <ChevronLeft size={18} />
              </button>
              <button
                onClick={handleNext}
                aria-label="Next Testimonial"
                className="w-8 h-8 rounded-full border border-white/15 bg-white/5 hover:bg-white/15 flex items-center justify-center text-white transition-colors cursor-pointer"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        </motion.div>

        {/* Testimonial Layout (Matching Reference Image Exactly) */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
          className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch"
        >
          
          {/* Left Column: Portrait Photo with rounded corners & light studio background */}
          <div className="lg:col-span-4 relative rounded-3xl overflow-hidden border border-white/15 bg-[#EAEAEA] shadow-2xl min-h-[380px] lg:min-h-[460px] flex items-center justify-center group">
            <img
              key={current.id}
              src={current.image}
              alt={current.name}
              className="w-full h-full object-cover object-center absolute inset-0 transition-all duration-500 animate-fadeIn"
            />
          </div>

          {/* Right Column: Dark Navy Gradient Card with Quote, Stats, and Name */}
          <div className="lg:col-span-8 bg-gradient-to-b from-[#0C1B3A] via-[#071126] to-[#040814] border border-white/15 rounded-3xl p-6 sm:p-8 md:p-10 shadow-2xl relative overflow-hidden flex flex-col justify-between hover:border-white/30 transition-all duration-300 min-h-[380px] lg:min-h-[460px]">
            
            {/* Soft Ambient Radial Blue Glow Overlay */}
            <div
              className="absolute top-0 right-0 w-[400px] h-[400px] pointer-events-none opacity-30 rounded-full blur-3xl"
              style={{
                background: 'radial-gradient(circle, rgba(0, 102, 255, 0.4) 0%, rgba(0, 40, 120, 0.1) 60%, transparent 80%)'
              }}
            />

            {/* Top Quote Block */}
            <div className="relative z-10 mb-6 sm:mb-10">
              <p className="text-base sm:text-xl md:text-2xl font-bold tracking-tight text-white uppercase leading-relaxed font-['DM_Sans']">
                {current.quote}
              </p>
            </div>

            {/* Middle Stats Row */}
            <div className="relative z-10 grid grid-cols-3 gap-3 sm:gap-6 my-auto py-6 border-t border-b border-white/10">
              {current.stats.map((stat, idx) => (
                <div key={idx} className="flex flex-col">
                  <div className="text-2xl sm:text-4xl md:text-5xl font-bold text-white tracking-tight font-['DM_Sans']">
                    {stat.value}
                  </div>
                  <div className="text-[10px] sm:text-xs text-white/60 font-medium tracking-wide font-['DM_Sans'] mt-1.5">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Bottom Person Credentials */}
            <div className="relative z-10 pt-4 flex flex-col justify-end">
              <span className="text-xs sm:text-sm font-bold tracking-widest text-white uppercase font-['DM_Sans']">
                — {current.name}
              </span>
              <span className="text-[11px] sm:text-xs text-white/60 font-medium tracking-wide font-['DM_Sans'] mt-0.5">
                {current.title}
              </span>
            </div>

          </div>

        </motion.div>

        {/* Sub-cards below: Quick toggle preview for all 3 testimonials */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.4 }}
          className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6 pt-6 border-t border-white/10"
        >
          {testimonials.map((t, idx) => (
            <div
              key={t.id}
              onClick={() => setActiveIndex(idx)}
              className={`p-4 rounded-2xl border transition-all cursor-pointer flex items-center gap-3 ${
                activeIndex === idx
                  ? 'bg-white/10 border-white/30 shadow-lg'
                  : 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 opacity-70 hover:opacity-100'
              }`}
            >
              <img
                src={t.image}
                alt={t.name}
                className="w-11 h-11 rounded-full object-cover border border-white/20"
              />
              <div className="overflow-hidden">
                <div className="text-xs font-bold text-white uppercase tracking-wider truncate font-['DM_Sans']">
                  {t.name}
                </div>
                <div className="text-[10px] text-white/60 truncate font-['DM_Sans']">
                  {t.title}
                </div>
              </div>
            </div>
          ))}
        </motion.div>

      </div>
    </section>
  );
}
