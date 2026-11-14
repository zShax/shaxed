// Default CV content for the home page. The admin (/admin#cv) can override it; "Reset to cv.js" brings this back.

export const person = {
  name: 'Marius Toma',
  location: 'Arad, Romania',
  email: 'marius.toma50@gmail.com',
  links: [
    { label: 'GitHub', text: 'github.com/zShax', href: 'https://github.com/zShax' },
    { label: 'LinkedIn', text: 'linkedin.com/in/marius1029', href: 'https://www.linkedin.com/in/marius1029' },
    { label: 'Links', text: 'solo.to/shax', href: 'https://solo.to/shax' },
  ],
};

export const hero = {
  marius: 'Full-stack web developer with a computer science degree. I turn repetitive office work into software that does it for you.',
  toma: 'Founder of Tela Creatrix. I built MailTempo and a few other things you can open right now.',
};

export const profile = [
  'I have a BSc in Computer Science, about a year and a half of full-stack web development behind me, and my own software company since December 2024.',
  'I build custom web applications, REST APIs, browser automations and AI/OCR data workflows that turn repetitive real-world processes into reliable tools. My background mixes computer science, years of customer-facing quality work, and economics. I am a first-year master’s student and I build with Claude Code.',
  'I ship in small increments: a median commit of about 115 lines, with roughly 3.5 features for every fix.',
];

export const experience = [
  {
    when: 'Feb 2026 – Sep 2026',
    role: 'Administrative (Data Entry)',
    org: 'Starplast Engineering SRL',
    points: [
      'Entered and validated real customer orders and business data in Microsoft Excel and the MAGO ERP system.',
      'Spotted the repetitive order-processing tasks and automated them with Playwright browser automations.',
      'Designed and built a full-stack web application, integrated with the company’s ERP, for automated order processing.',
      'Built AI/OCR workflows that pull structured order data out of customer PDF documents, plus the validation logic that prepares it for the ERP.',
      'The system processed 895 real customer orders, with 374 skipped and 0 left unprocessed at the time of measurement.',
    ],
    tech: 'JavaScript, Node.js, Playwright, PostgreSQL, Prisma, REST APIs, AI/OCR, Claude Desktop (connectors, skills and plugins), Claude Code, Excel, MAGO ERP',
  },
  {
    when: 'Dec 2024 – present',
    role: 'Founder and full-stack developer',
    org: 'Tela Creatrix SRL',
    points: [
      'Founded and built MailTempo, an AI-powered email-marketing SaaS for contact management, segmentation, personalization and campaign automation.',
      'Built the full stack: frontend, backend, REST APIs, authentication, PostgreSQL database and third-party integrations.',
      'Handle product decisions, deployment and ongoing development on my own, plus custom software projects for clients.',
      'Built and set up many internal tools, such as full email apps integrated with Resend and the Cloudflare CLI.',
      'Shipped 17 new projects in 2026 (about 500 commits across Shopify, WooCommerce, mapping and automation work), sustaining weekly output for 45 consecutive weeks.',
      'Took projects from an empty repo to a deployed, multi-feature product in 3 to 6 days, for example a storefront plus automated catalog sync in under 3 days.',
    ],
    tech: 'Node.js, Express.js, Next.js, React, PostgreSQL, Prisma, PM2, Nginx, Docker, REST APIs, AI integrations, VPS management',
  },
  {
    when: 'Jan 2024 – May 2025',
    role: 'Web developer',
    org: 'Steelmonks',
    note: 'Full-time, Arad',
    points: [
      'Oversaw, maintained and updated 6 Shopify stores and websites: steelmonks.com and 5 sub-brands.',
      'Built a web platform with 3 internal apps from scratch (Node.js, Express, TypeScript, PostgreSQL). The production team still uses it daily.',
      'Centralized the codebases of all websites on GitHub and organized developer workflows so they scale.',
      'Customized Shopify themes with Liquid and integrated Shopify apps and third-party services.',
      'Set up analytics and conversion tracking with Google Tag Manager, GA4 and ad pixels (TikTok, Meta, Google, Pinterest); designed A/B tests.',
      'Designed and built campaign pages, debugged production issues and optimized performance.',
    ],
    tech: 'JavaScript, TypeScript, React, Node.js, Express.js, PostgreSQL, Webpack, GitHub, HTML5, CSS3, SCSS, Tailwind CSS, Shopify Liquid and custom plugins, Lighthouse, Shogun, Elementor, REST and GraphQL APIs',
  },
  {
    when: 'Jun 2023 – Aug 2023',
    role: 'Sales associate and host',
    org: 'Big Bus Tours, Applebee’s',
    note: 'San Francisco, J-1 Work & Travel',
    points: [
      'Became a top seller at Big Bus Tours after the first month.',
      'Worked with an international customer base and adapted to a new cultural and professional environment.',
    ],
  },
  {
    when: 'Nov 2021 – May 2023',
    role: 'Customer service ambassador, then subject matter expert, then customer experience analyst',
    org: 'TELUS International',
    note: 'Remote, promoted twice',
    points: [
      'Customer service ambassador (Nov 2021 – Oct 2022): supported customers by phone and email in Italian and English; top performer within the first month.',
      'Subject matter expert (Oct 2022 – Dec 2022): resolved escalated cases, gave remote floor support, and created or improved 100+ standardized procedures that lowered resolution times.',
      'Customer experience analyst (Dec 2022 – May 2023): analyzed KPI data for two teams (about 15 people) for coaching and training, and presented it to operations in weekly cross-department meetings.',
    ],
  },
];

// The "open it right now" list. `href` is what the row links to, `domain` is what it shows.
export const liveProjects = [
  {
    domain: 'arad.shaxed.com',
    href: 'https://arad.shaxed.com/',
    name: 'Confirm Humanity',
    what: 'Connects volunteers, professionals and people looking for social events with the communities in Arad that need them. Third place at Hack4Arad 2026 with 10+ real users in a week.',
  },
  {
    domain: 'getmailtempo.com',
    href: 'https://getmailtempo.com/',
    name: 'MailTempo',
    what: 'AI-powered email marketing: contacts, segments, personalization and campaign automation. Founded and built through Tela Creatrix.',
  },
  {
    domain: 'app.getmailtempo.com',
    href: 'https://app.getmailtempo.com/',
    name: 'MailTempo app',
    what: 'The product itself. Sign in to manage contacts and send campaigns.',
  },
  {
    domain: 'leads.shaxed.com',
    href: 'https://leads.shaxed.com/',
    name: 'Lead Finder',
    what: 'A dashboard for finding and tracking business leads.',
  },
];

export const privateProjects = [
  {
    name: 'Automated order processing',
    what: 'Production app at Starplast: AI/OCR extraction from customer order PDFs, validation and ERP integration. 895 real orders processed.',
  },
  {
    name: 'Scanning process',
    what: 'Production-management web app that tracks manufacturing orders with barcode scanning.',
  },
];

export const education = [
  { what: 'Master’s degree, IASTE', where: '“Aurel Vlaicu” University of Arad', when: '2026 – 2027, first year' },
  { what: 'BSc in Computer Science', where: '“Aurel Vlaicu” University of Arad', when: 'Three-year programme, completed' },
  { what: 'Eight-month intensive coding course', where: 'GoIT Romania', when: 'Graduate' },
  { what: 'Baccalaureate in Commerce', where: '“Colegiul Economic Arad” High School', when: '2017 – 2021' },
];

export const skills = [
  { group: 'Web development', items: 'JavaScript (Node.js, Express.js, vanilla JS), React, Next.js, HTML5, CSS3, SCSS, Tailwind CSS, PHP (basic to intermediate), REST API design and integration' },
  { group: 'Backend and databases', items: 'PostgreSQL with Prisma, authentication and sessions, third-party API integrations' },
  { group: 'Automation and AI', items: 'Playwright browser automation, AI/OCR workflows, PDF data extraction, AI-assisted development (Claude Code, Cursor)' },
  { group: 'E-commerce and analytics', items: 'WordPress and WooCommerce, Shopify themes and Liquid, Google Tag Manager, GA4, ad pixels, A/B testing, conversion optimization' },
  { group: 'Tools', items: 'Git (GitHub, GitLab), basic Docker, Cloudflare Workers, Agile workflows, client management' },
];

export const awards = [
  { what: 'Club President, Toastmasters Arad', detail: 'One-year term, August 2026 to July 2027. Also Contest Chair for the English Table Topics contest, October 2026.' },
  { what: 'Hack4Arad 2026', detail: 'Third place with Confirm Humanity.' },
  { what: 'Hack4Arad 2023', detail: '48-hour hackathon. Won the “Smart Public Transport” prize.' },
  { what: 'StudMath-IT International Student Conference', detail: 'Third prize and a Certificate of Appreciation from ISIDORS in 2022, third prize in 2023, taking part again in 2026.' },
  { what: 'Research volunteer', detail: '“Romanian People’s Confidence in Cryptocurrency Investments”, a project of Prof. Crina Anina Bejan, PhD, 2022.' },
];

export const languages = [
  { name: 'Romanian', level: 'native' },
  { name: 'Italian', level: 'C1' },
  { name: 'English', level: 'B2' },
  { name: 'Spanish', level: 'A2' },
];

// "At a glance": the four big figures.
export const numbers = [
  { figure: '17', label: 'projects shipped in 2026', detail: 'About 500 commits across Shopify, WooCommerce, mapping and automation work.' },
  { figure: '45', label: 'weeks in a row', detail: 'Weekly output sustained for 45 consecutive weeks.' },
  { figure: '895', label: 'customer orders', detail: 'Run through the order-processing app I built at Starplast. None left unprocessed.' },
  { figure: '100+', label: 'standard procedures', detail: 'Written or improved at TELUS International. They cut resolution times.' },
  { figure: '6 + 3', label: 'stores and apps', detail: 'Six Shopify stores kept running and three internal apps built from scratch at Steelmonks.' },
  { figure: '4', label: 'prizes', detail: 'From hackathons and student conferences, 2022 to 2026.' },
];

// "Where the years went". from/to are YYYY-MM; leave `to` empty for "still going".
// kind: work, own (my company), study, lead.
export const timeline = [
  { label: 'TELUS International', what: 'Customer service to analyst', kind: 'work', from: '2021-11', to: '2023-05' },
  { label: 'GoIT Romania', what: 'Intensive coding course', kind: 'study', from: '2023-01', to: '2023-08' },
  { label: 'San Francisco', what: 'Big Bus Tours, Applebee’s', kind: 'work', from: '2023-06', to: '2023-08' },
  { label: 'BSc Computer Science', what: '“Aurel Vlaicu” University', kind: 'study', from: '2023-10', to: '2026-07' },
  { label: 'Steelmonks', what: 'Web developer', kind: 'work', from: '2024-01', to: '2025-05' },
  { label: 'Tela Creatrix', what: 'Founder, MailTempo', kind: 'own', from: '2024-12', to: '' },
  { label: 'Starplast Engineering', what: 'Data entry, then automation', kind: 'work', from: '2026-02', to: '2026-09' },
  { label: 'Toastmasters Arad', what: 'Club President', kind: 'lead', from: '2026-08', to: '2027-07' },
  { label: 'Master’s, IASTE', what: '“Aurel Vlaicu” University', kind: 'study', from: '2026-10', to: '2027-07' },
];

// "What I use, and where". usedAt is a comma-separated list; each name becomes a column.
export const skillMap = [
  { area: 'Full-stack web', tools: 'React, Next.js, Node.js, Express', usedAt: 'Starplast, Tela Creatrix, Steelmonks' },
  { area: 'Automation and AI/OCR', tools: 'Playwright, Claude, PDF extraction', usedAt: 'Starplast, Tela Creatrix' },
  { area: 'Databases and servers', tools: 'PostgreSQL, Prisma, Docker, Nginx', usedAt: 'Starplast, Tela Creatrix, Steelmonks' },
  { area: 'E-commerce and growth', tools: 'Shopify Liquid, GTM, GA4, A/B tests, email campaigns', usedAt: 'Tela Creatrix, Steelmonks' },
  { area: 'Data and people', tools: 'KPI analysis, procedures, coaching, public speaking', usedAt: 'Starplast, TELUS, Toastmasters' },
];

export const interests ='Artificial intelligence and AI safety, automation, software architecture, SaaS. Away from the screen: chess, climbing, ping pong, hiking.';
