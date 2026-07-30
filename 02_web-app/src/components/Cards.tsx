import { Target, Crosshair, Video, Cpu, Activity, Sparkles } from 'lucide-react';
import { motion } from 'motion/react';

export function Cards() {
  const cardData = [
    {
      title: "The Problem We're Solving",
      icon: Target,
      content: "Veterinary suturing is traditionally taught through direct observation, making it hard to consistently track technique, timing, and instrument use. Our system brings AI-powered visual analysis to the operating table, turning raw procedure footage into structured, trackable data."
    },
    {
      title: "What the System Detects",
      icon: Crosshair,
      content: "Trained to recognize five key elements of every suturing procedure — the needle, the operator's hand, the needle holder, the wound area, and the forceps — the model identifies not just what instrument is in frame, but exactly where it is."
    },
    {
      title: "From Video to Vision",
      icon: Video,
      content: "Every procedure starts as raw video. Our pipeline extracts frames at set intervals, transforms them into structured, annotated training data, and feeds them into a deep learning model — turning hours of footage into a system that sees what a trained eye sees."
    },
    {
      title: "Built on YOLOv11",
      icon: Cpu,
      content: "Powered by YOLOv11 (Accurate), one of the most capable real-time object detection architectures available, the model learns to recognize instrument shapes, positions, and context across hundreds of annotated training examples."
    },
    {
      title: "Phase 1 Results",
      icon: Activity,
      content: "In its first phase, the system was trained on 12 surgical videos and 120 fully annotated frames, achieving 68.1% mAP@50, 80.5% precision, and 73.1% recall — a strong early benchmark for a first-generation detection model."
    },
    {
      title: "What's Next",
      icon: Sparkles,
      content: "Phase 2 expands the dataset with greater diversity in animal type, wound size, camera angle, and lighting — while introducing data augmentation and early development of RNN-based models to analyze movement sequences over time, paving the way toward real-time, in-theater deployment."
    }
  ];

  const containerVariants = {
    hidden: {},
    visible: {
      transition: {
        staggerChildren: 0.15
      }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 30 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" } }
  };

  return (
    <section className="relative z-10 w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-2 pb-4">
      <motion.div 
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-100px" }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch"
      >
        {cardData.map((card, idx) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={idx}
              variants={itemVariants}
              className="bg-white/10 border border-white/15 backdrop-blur-md rounded-2xl p-4 sm:p-5 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 group"
            >
              <div>
                {/* White square icon badge */}
                <div className="bg-white p-2 rounded-lg w-9 h-9 flex items-center justify-center mb-3 shadow-md group-hover:scale-105 transition-transform">
                  <Icon className="w-4 h-4 text-[#0066FF]" />
                </div>

                <h2 className="text-base sm:text-lg font-medium text-white mb-2 tracking-tight font-['DM_Sans']">
                  {card.title}
                </h2>

                <p className="text-white/90 text-xs sm:text-sm leading-relaxed font-['DM_Sans'] font-normal">
                  {card.content}
                </p>
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </section>
  );
}


