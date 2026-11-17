/* PRAHARI · Bengali (বাংলা) dictionary
   ─────────────────────────────────────────────────────────────────────────
   STATUS: DRAFT — written for review, not yet reviewed.
   Before a Bengal pilot, a native Bengali speaker who works with farmers
   (ideally a KVK / Krishi Prayukti Sahayak) must read every line below. Mark
   the review in docs/BENGAL_CROP_VALIDATION.md, not here.

   How it works. The app's existing helper is bi(lang, english, marathi). For
   lang === 'bn' it looks the ENGLISH string up here. A string that is missing
   falls back to English — never to Marathi and never to a guess — so a gap
   shows up as English on the screen, which a reviewer can see and fix.

   Rules used while writing it:
   · Plain spoken Bengali a farmer uses, not literary or sanskritised words
     (e.g. "পোকা", not "কীটপতঙ্গ"; "স্প্রে", which farmers say, not
     "ছিটানো" everywhere).
   · "Taluka" is not a Bengal unit. The administrative unit is the block, so
     it is rendered "ব্লক".
   · Model and scientific names (Hutton, TOMCAST, Phytophthora infestans,
     JHULSACAST) are never translated.
   · Numbers stay as the app prints them. Nothing here may change a number,
     a unit or an agronomic meaning.
   · ETL is kept as "ইটিএল" with the full phrase where there is room.

   Keyed by the exact English source string. If the English changes, this
   entry stops matching and the screen shows English again — safe by design. */

const BN = {
  // ── app shell ─────────────────────────────────────────────────────────
  'Loading…': 'লোড হচ্ছে…',
  'Sign out': 'সাইন আউট',
  'Register a field first': 'আগে একটি জমি নথিভুক্ত করুন',
  'PRAHARI needs a location, a crop and a sowing date before it can forecast anything.':
    'কিছু পূর্বাভাস দেওয়ার আগে প্রহরীর জমির অবস্থান, ফসল আর বোনার তারিখ জানা দরকার।',
  'Add a field': 'জমি যোগ করুন',

  // ── shared states (ui.jsx) ────────────────────────────────────────────
  'Risk forecast needs more past weather than is available':
    'ঝুঁকির পূর্বাভাসের জন্য যত দিনের পুরনো আবহাওয়া লাগে, তত দিনের তথ্য এখনও পাওয়া যায়নি',
  'Weather update temporarily unavailable': 'আবহাওয়ার খবর এই মুহূর্তে পাওয়া যাচ্ছে না',
  'Try again': 'আবার চেষ্টা করুন',
  'The camera is not available. Use the button below to choose a photo.':
    'ক্যামেরা চালু হচ্ছে না। নিচের বোতাম টিপে গ্যালারি থেকে ছবি বেছে নিন।',
  'Fill the frame with one leaf': 'ফ্রেম জুড়ে একটি পাতা রাখুন',
  'Tips for best result': 'ভালো ছবির জন্য',
  'Gallery': 'গ্যালারি',
  'Take photo': 'ছবি তুলুন',
  'Light': 'আলো',
  'DEMO MODE — weather is generated, not observed.':
    'ডেমো মোড — এই আবহাওয়া তৈরি করা, মাপা নয়।',
  'en-IN': 'bn-IN',

  // ── sign in ───────────────────────────────────────────────────────────
  'Password changed. Sign in now.': 'পাসওয়ার্ড বদলানো হয়েছে। এবার সাইন ইন করুন।',
  'Send reset code': 'রিসেট কোড পাঠান',
  'Change password': 'পাসওয়ার্ড বদলান',
  'Explore without an account — demo': 'অ্যাকাউন্ট ছাড়া দেখে নিন — ডেমো',
  'Demo accounts are real accounts on live weather — not yours, and shared.':
    'ডেমো অ্যাকাউন্টগুলি আসল আবহাওয়ায় চলে — এগুলো আপনার নয়, সবাই ব্যবহার করে।',
  'Your field data is yours: it is never shown to another farmer, and taluka surveillance is aggregated so no individual farm can be identified.':
    'আপনার জমির তথ্য আপনারই। অন্য কোনো কৃষককে তা দেখানো হয় না, আর ব্লক স্তরের নজরদারিতে সব তথ্য একসঙ্গে গোনা হয়, তাই কোনো একটি জমিকে আলাদা করে চেনা যায় না।',

  'This is a demo service: synthetic farmers and generated, labelled weather. The engines are the production ones.':
    'এটি ডেমো পরিষেবা: কৃত্রিম কৃষক আর তৈরি করা, চিহ্নিত আবহাওয়া। হিসাবের পদ্ধতিগুলি আসল পরিষেবার মতোই।',

  // ── home ──────────────────────────────────────────────────────────────
  'No field registered yet': 'এখনও কোনো জমি নথিভুক্ত হয়নি',
  'Farm Health': 'জমির স্বাস্থ্য',
  'Weather': 'আবহাওয়া',
  'Pest': 'পোকা',
  'Disease': 'রোগ',
  'How is this number built?': 'এই সংখ্যা কীভাবে হিসাব হয়?',
  'My next best action': 'আমার পরের সবচেয়ে জরুরি কাজ',
  'Also due today': 'আজ আরও যা করার',
  'What should I do today?': 'আজ আমি কী করব?',
  'Nothing needs a decision today.': 'আজ কোনো সিদ্ধান্ত নেওয়ার দরকার নেই।',
  'How this list is built': 'এই তালিকা কীভাবে তৈরি হয়',
  "What's Coming": 'সামনে কী আসছে',
  'Details': 'বিস্তারিত',
  'Today': 'আজ',
  'How this is scored': 'কীভাবে নম্বর দেওয়া হয়',
  'Crop Health Passport': 'ফসলের স্বাস্থ্য-পাসপোর্ট',
  'History': 'ইতিহাস',
  'Every scan, count, decision and application this season. At harvest, this is the record that shows what was used and when.':
    'এই মরসুমের প্রতিটি স্ক্যান, গণনা, সিদ্ধান্ত আর প্রয়োগ। ফসল তোলার সময় এই খাতাই দেখায় কী, কবে ব্যবহার হয়েছিল।',
  'How PRAHARI works': 'প্রহরী কীভাবে কাজ করে',
  'Prediction to action, in seven steps': 'পূর্বাভাস থেকে কাজ — সাতটি ধাপে',
  'PRAHARI is an early-warning tool. The decision is yours — and when it is unclear, ask your Krishi Sahayak.':
    'প্রহরী আগাম সতর্কবার্তা দেয়। সিদ্ধান্ত আপনার — আর বুঝতে না পারলে আপনার কৃষি প্রযুক্তি সহায়ককে জিজ্ঞাসা করুন।',
  'today': 'আজ',
  'yesterday': 'গতকাল',
  'Scans': 'স্ক্যান',
  'Counts': 'গণনা',
  'Checks': 'পরিদর্শন',
  'Sprays': 'স্প্রে',
  'Follow-ups': 'পুনঃপরীক্ষা',
  'Expert': 'বিশেষজ্ঞ',
  'No crop': 'ফসল নেই',
  'Stage not known — no sowing date on record': 'বৃদ্ধির ধাপ জানা নেই — বোনার তারিখ নথিতে নেই',
  'Health': 'স্বাস্থ্য',
  'first reading': 'প্রথম মাপ',
  'Not scored': 'নম্বর দেওয়া হয়নি',
  'Top threat': 'সবচেয়ে বড় বিপদ',
  'Nothing firing': 'এখন কোনো সতর্কতা নেই',
  'Not forecast — no weather': 'পূর্বাভাস নেই — আবহাওয়ার তথ্য নেই',
  'Last checked': 'শেষ পরীক্ষা',
  'Do next': 'এরপর করুন',
  'Nothing needs doing today. Keep walking the field.': 'আজ কিছু করার নেই। নিয়মিত জমি ঘুরে দেখতে থাকুন।',
  'Nothing recorded for this crop yet. Scan a leaf or count a trap and it starts filling in — at harvest this is the record of what was used and when.':
    'এই ফসলের জন্য এখনও কিছু লেখা হয়নি। একটি পাতা স্ক্যান করুন বা ফাঁদের পোকা গুনুন, তাহলেই খাতা ভরতে শুরু করবে — ফসল তোলার সময় এটাই দেখাবে কী, কবে ব্যবহার হয়েছিল।',
  'Register your first field': 'আপনার প্রথম জমি নথিভুক্ত করুন',
  'Give PRAHARI a location, a crop and a sowing date, and it starts forecasting risk from the real weather at that exact spot.':
    'জমির অবস্থান, ফসল আর বোনার তারিখ দিন — প্রহরী ঠিক সেই জায়গার আসল আবহাওয়া থেকে ঝুঁকির পূর্বাভাস দিতে শুরু করবে।',

  // ── scan, photo quality, diagnosis, refusal ───────────────────────────
  'Scan Crop': 'ফসল স্ক্যান',
  'Diagnosis Result': 'রোগ নির্ণয়ের ফল',
  'Measuring the leaf…': 'পাতা মাপা হচ্ছে…',
  'Segmenting the leaf, then measuring lesion area, chlorosis and powder inside it.':
    'ছবি থেকে পাতাটুকু আলাদা করে তার মধ্যে দাগের জায়গা, হলুদ ভাব আর সাদা গুঁড়ো মাপা হচ্ছে।',
  'Take another photo': 'আরেকটি ছবি তুলুন',
  'Later': 'পরে',
  "We can't reliably analyse this photograph": 'এই ছবি থেকে নির্ভরযোগ্যভাবে কিছু বলা যাচ্ছে না',
  'PRAHARI has not diagnosed anything from this image. Refusing a bad photograph is safer than guessing on one.':
    'এই ছবি থেকে প্রহরী কোনো রোগ বলেনি। খারাপ ছবি দেখে আন্দাজ করার চেয়ে না বলাই নিরাপদ।',
  'Do this': 'এটা করুন',
  'What was measured?': 'কী মাপা হয়েছে?',
  'The camera cannot answer this': 'ক্যামেরা দিয়ে এর উত্তর পাওয়া যায় না',
  'Your observation is recorded. The weather and threshold engines carry the advisory, and you can send this case to an expert.':
    'আপনার পর্যবেক্ষণ লেখা হয়েছে। পরামর্শ আসবে আবহাওয়া আর ক্ষতির সীমার হিসাব থেকে, আর চাইলে এই কেসটি বিশেষজ্ঞকে পাঠাতে পারেন।',
  'Uncertain — not confident enough': 'নিশ্চিত নয় — যথেষ্ট ভরসা নেই',
  'Likely issue': 'সম্ভাব্য সমস্যা',
  'Confidence': 'নিশ্চয়তা',
  'No confident diagnosis': 'নিশ্চিত কোনো রোগ বলা যাচ্ছে না',
  'PRAHARI is not confident enough to name this': 'নাম বলার মতো যথেষ্ট নিশ্চিত নয় প্রহরী',
  'Engine': 'যে পদ্ধতিতে বিচার হয়েছে',
  'Alternative Possibilities': 'অন্য সম্ভাবনা',
  'PRAHARI never forces one answer. Every candidate is shown with its confidence.':
    'প্রহরী জোর করে একটাই উত্তর দেয় না। প্রতিটি সম্ভাবনা তার নিশ্চয়তা সহ দেখানো হয়।',
  'Evidence Found': 'যে প্রমাণ পাওয়া গেছে',
  'How was this ranked?': 'এই ক্রম কীভাবে ঠিক হলো?',
  'A few questions': 'কয়েকটি প্রশ্ন',
  'These ask what the photograph cannot show. Your answers may settle it.':
    'ছবিতে যা দেখা যায় না, এই প্রশ্নগুলি তা জানতে চায়। আপনার উত্তরে বিষয়টা পরিষ্কার হতে পারে।',
  'Submit answers': 'উত্তর জমা দিন',
  'Your answers settled it': 'আপনার উত্তরে বিষয়টা পরিষ্কার হয়েছে',
  'Still not decisive': 'এখনও নিশ্চিত হওয়া যায়নি',
  'Sending this to an expert is the right next step.': 'এবার বিশেষজ্ঞকে পাঠানোই ঠিক পদক্ষেপ।',
  "What's Next?": 'এরপর কী?',
  'View management': 'ব্যবস্থাপনা দেখুন',
  'Scan another leaf': 'আরেকটি পাতা স্ক্যান করুন',
  'An agronomist will review the photograph, the weather at your field and its history.':
    'একজন কৃষি বিশেষজ্ঞ ছবি, আপনার জমির আবহাওয়া আর জমির ইতিহাস দেখে বিচার করবেন।',
  '👨‍🌾 Request expert review': '👨‍🌾 বিশেষজ্ঞের মতামত চান',
  'Add another photograph': 'আরেকটি ছবি যোগ করুন',
  'A photograph showing something the first one did not can improve the answer. Re-sending the same view will not.':
    'প্রথম ছবিতে যা দেখা যায়নি, এমন কিছু দেখালে উত্তর ভালো হতে পারে। একই দিক থেকে আবার ছবি পাঠালে লাভ হবে না।',
  'That photograph could not be used': 'ওই ছবিটি ব্যবহার করা যায়নি',
  'It has been saved to this observation, but it was not fed to the engine.':
    'ছবিটি এই পর্যবেক্ষণের সঙ্গে রাখা হয়েছে, কিন্তু বিচারের জন্য ব্যবহার করা হয়নি।',

  // ── fields, onboarding, crop selection ────────────────────────────────
  'My Crops': 'আমার ফসল',
  'My Fields': 'আমার জমি',
  'Field': 'জমি',
  'Choose a field to open its crop journey.': 'ফসলের যাত্রাপথ দেখতে একটি জমি বেছে নিন।',
  'No fields yet': 'এখনও কোনো জমি নেই',
  'Register a field and PRAHARI starts forecasting risk from the real weather at that exact spot. You can add as many as you farm, each with its own crop.':
    'একটি জমি নথিভুক্ত করুন — প্রহরী ঠিক সেই জায়গার আসল আবহাওয়া থেকে ঝুঁকির পূর্বাভাস দেবে। যতগুলো জমিতে চাষ করেন, সব যোগ করতে পারেন, প্রতিটির নিজের ফসল সহ।',
  'Live status could not be loaded. Your fields are listed below.':
    'এই মুহূর্তের অবস্থা আনা যায়নি। আপনার জমিগুলি নিচে দেওয়া আছে।',
  'Add another field': 'আরেকটি জমি যোগ করুন',
  'How this board is built': 'এই তালিকা কীভাবে সাজানো হয়',
  'Start a new crop': 'নতুন ফসল শুরু করুন',
  'Crop': 'ফসল',
  'Sown on': 'বোনার তারিখ',
  'The crop stage, and every threshold that depends on it, is counted from this date.':
    'ফসলের বৃদ্ধির ধাপ আর তার উপর নির্ভরশীল প্রতিটি সীমা এই তারিখ থেকে হিসাব হয়।',
  'Variety (optional)': 'জাত (ইচ্ছামতো)',
  'Start this crop': 'এই ফসল শুরু করুন',
  'Cancel': 'বাতিল',
  'more': 'আরও',
  'Nothing needed today': 'আজ কিছু করার নেই',
  'Not scouted yet': 'এখনও জমি পরিদর্শন হয়নি',
  'Journey': 'যাত্রাপথ',
  'Traps': 'ফাঁদ',
  'New crop': 'নতুন ফসল',
  'Field name': 'জমির নাম',
  'Area (acres)': 'আয়তন (একর)',
  'Sowing date': 'বোনার তারিখ',
  'Where is the field?': 'জমিটি কোথায়?',
  'PRAHARI forecasts risk from the real weather at this exact spot. GPS is best if you are standing in the field.':
    'প্রহরী ঠিক এই জায়গার আসল আবহাওয়া থেকে ঝুঁকি হিসাব করে। জমিতে দাঁড়িয়ে থাকলে জিপিএস ব্যবহার করাই সবচেয়ে ভালো।',
  'Finding your location…': 'আপনার অবস্থান খোঁজা হচ্ছে…',
  'Use my current location': 'আমার এখনকার অবস্থান ব্যবহার করুন',
  'Location captured': 'অবস্থান পাওয়া গেছে',
  'Could not get a location. Choose a taluka below — PRAHARI will use the taluka centroid instead, and will say so.':
    'অবস্থান পাওয়া যায়নি। নিচ থেকে ব্লক বেছে নিন — প্রহরী তখন ব্লকের কেন্দ্রের অবস্থান ধরবে, এবং সেটা স্পষ্ট করে জানাবে।',
  'Taluka': 'ব্লক',
  'Use my account taluka': 'আমার অ্যাকাউন্টের ব্লক ব্যবহার করুন',
  'Village (optional)': 'গ্রাম (ইচ্ছামতো)',
  'Farming details (optional)': 'চাষের বিবরণ (ইচ্ছামতো)',
  'Soil': 'মাটি',
  'Irrigation': 'সেচ',
  'Your knapsack sprayer (litres)': 'আপনার পিঠে-বাঁধা স্প্রে মেশিন (লিটার)',
  'Doses are worked out in your own tank size, not in litres per hectare.':
    'মাত্রা হিসাব হয় আপনার নিজের ট্যাঙ্কের মাপে, হেক্টর প্রতি লিটারে নয়।',
  'Register field': 'জমি নথিভুক্ত করুন',
  'Field Health Passport': 'জমির স্বাস্থ্য-পাসপোর্ট',
  'Crop health score over time': 'সময়ের সঙ্গে ফসলের স্বাস্থ্য-নম্বর',
  'Everything that happened to this field': 'এই জমিতে যা যা হয়েছে',
  'Nothing recorded yet': 'এখনও কিছু লেখা হয়নি',

  // ── IPM decision screen ───────────────────────────────────────────────
  'Scan the crop': 'ফসল স্ক্যান করুন',
  'Ticking is only for you. Recording a count or an inspection is what moves the decision.':
    'টিক দেওয়া শুধু আপনার মনে রাখার জন্য। সিদ্ধান্ত বদলায় গণনা বা পরিদর্শন নথিভুক্ত করলে।',
  'Demo weather': 'ডেমো আবহাওয়া',
  'Walk the field early rather than spraying early.': 'আগেভাগে স্প্রে না করে আগেভাগে জমি ঘুরে দেখুন।',
  'Scan again': 'আবার স্ক্যান করুন',
  'Count the same trap so the two numbers can be compared.': 'একই ফাঁদের পোকা গুনুন, যাতে দুটো সংখ্যা মেলানো যায়।',
  'Photograph the same plant so the two pictures can be compared.': 'একই গাছের ছবি তুলুন, যাতে দুটো ছবি মেলানো যায়।',
  'Nothing here needs an expert right now.': 'এই মুহূর্তে এখানে বিশেষজ্ঞের দরকার নেই।',
  'Ask an expert': 'বিশেষজ্ঞকে জিজ্ঞাসা করুন',
  'Your scan and this field’s record go with the question.': 'প্রশ্নের সঙ্গে আপনার স্ক্যান আর এই জমির খাতাও যাবে।',
  'No verified chemical recommendation': 'যাচাই করা কোনো রাসায়নিক সুপারিশ নেই',
  'Why not?': 'কেন নেই?',
  'Withheld': 'দেওয়া হয়নি',
  'Where this threshold comes from': 'এই সীমা কোথা থেকে এসেছে',
  'About this weather': 'এই আবহাওয়া সম্পর্কে',
  'per trap': 'প্রতি ফাঁদে',
  'threshold': 'সীমা',
  'Assess the field': 'জমি পরিদর্শন করুন',
  'Walk the field, look at a set number of plants, and record how many show it.':
    'জমি ঘুরে নির্দিষ্ট সংখ্যক গাছ দেখুন, আর কতগুলিতে লক্ষণ আছে তা লিখুন।',
  'Plants inspected': 'যত গাছ দেখা হয়েছে',
  'Showing symptoms': 'লক্ষণ আছে',
  'of the plants you looked at': 'আপনি যত গাছ দেখেছেন তার মধ্যে',
  'More plants are marked affected than were inspected.': 'যত গাছ দেখেছেন, আক্রান্ত লেখা হয়েছে তার চেয়ে বেশি।',
  'How far it has gone on an affected plant': 'আক্রান্ত গাছে রোগ কতটা ছড়িয়েছে',
  'Where': 'কোথায়',
  'Save assessment': 'পরিদর্শন সংরক্ষণ করুন',
  'A band, never a percentage you had to estimate. Nobody measures leaf area standing in a field.':
    'একটি মোটামুটি ভাগ বেছে নিন — আন্দাজ করে শতাংশ নয়। জমিতে দাঁড়িয়ে কেউ পাতার মাপ নেয় না।',
  'Blocked': 'বন্ধ',
  'Allowed': 'অনুমোদিত',
  'Dose': 'মাত্রা',
  'Recorded': 'নথিভুক্ত',
  'Follow-up scan due': 'পুনঃস্ক্যানের সময় হয়েছে',
  'harvest gated until': 'এই তারিখ পর্যন্ত ফসল তোলা যাবে না',
  'Done': 'হয়ে গেছে',
  'I applied this — record it': 'আমি এটা প্রয়োগ করেছি — লিখে রাখুন',
  'Recording it sets the pre-harvest gate and schedules the re-scan five days from now.':
    'নথিভুক্ত করলে ফসল তোলার আগের অপেক্ষার সময় ঠিক হয়ে যায়, আর পাঁচ দিন পরে পুনঃস্ক্যানের দিন ধার্য হয়।',
  'Record a count': 'গণনা লিখুন',
  'You are offline. This count is saved on your phone and will be sent when you reconnect — it cannot be counted twice.':
    'আপনি এখন অফলাইন। গণনাটি ফোনে রাখা আছে, নেট এলে পাঠানো হবে — দু-বার গোনা হবে না।',
  'Save count': 'গণনা সংরক্ষণ করুন',
  'This works offline — it will sync later.': 'এটা অফলাইনেও চলে — পরে পাঠানো হবে।',

  // ── weather card ──────────────────────────────────────────────────────
  'These numbers are generated, not observed — the live weather service could not be reached. They are consistent and repeatable, and they are not a measurement of your field.':
    'এই সংখ্যাগুলি তৈরি করা, মাপা নয় — আসল আবহাওয়া পরিষেবায় পৌঁছানো যায়নি। এগুলি আপনার জমির মাপ নয়।',
  'The forecast is live. The risk board needs more past weather than this plan provides, so it is shown separately.':
    'পূর্বাভাস আসল আবহাওয়া থেকে। কিন্তু ঝুঁকির হিসাবের জন্য যত দিনের পুরনো আবহাওয়া লাগে, তা এখন পাওয়া যাচ্ছে না, তাই তা আলাদা করে দেখানো হচ্ছে।',

  // ── risk forecast, traps, alerts, follow-up, profile ──────────────────
  'Risk Forecast': 'ঝুঁকির পূর্বাভাস',
  'Disease Risk': 'রোগের ঝুঁকি',
  'Pest Risk': 'পোকার ঝুঁকি',
  'Next 4 days': 'আগামী ৪ দিন',
  'Contributing weather': 'যে আবহাওয়া ঝুঁকি বাড়াচ্ছে',
  'Hours at RH ≥ 90%': 'আপেক্ষিক আর্দ্রতা ≥ ৯০% থাকা ঘণ্টা',
  'Rainfall': 'বৃষ্টি',
  'Night minimum': 'রাতের সর্বনিম্ন তাপমাত্রা',
  'What to look for': 'কী দেখবেন',
  'What model is this?': 'এটা কোন মডেল?',
  'No pest model for this crop': 'এই ফসলের জন্য পোকার কোনো মডেল নেই',
  'Damaging stage': 'ক্ষতিকর ধাপ',
  'Spray cannot reach it': 'স্প্রে সেখানে পৌঁছায় না',
  'Current life stage': 'এখনকার জীবনচক্রের ধাপ',
  'Economic threshold': 'অর্থনৈতিক ক্ষতির সীমা (ইটিএল)',
  'Should I spray?': 'স্প্রে করব কি?',
  'Pest Trap Monitor': 'পোকার ফাঁদ পর্যবেক্ষণ',
  'No traps installed': 'কোনো ফাঁদ বসানো হয়নি',
  'A trap count is the only evidence that can justify an intervention. A photograph alone cannot.':
    'শুধু ফাঁদের গণনাই ব্যবস্থা নেওয়ার যুক্তি দিতে পারে। শুধু ছবি তা পারে না।',
  'Add a trap': 'ফাঁদ যোগ করুন',
  "Today's count": 'আজকের গণনা',
  'High': 'বেশি',
  'Below ETL': 'ইটিএলের নিচে',
  'ETL': 'ইটিএল',
  'Threshold crossed': 'সীমা পেরিয়ে গেছে',
  'Open the IPM options. A chemical appears only if a verified label claim exists for this crop and pest.':
    'আইপিএম-এর উপায়গুলি দেখুন। এই ফসল আর পোকার জন্য যাচাই করা লেবেল-অনুমোদন থাকলে তবেই কোনো রাসায়নিক দেখানো হবে।',
  'Add a trap count': 'ফাঁদের গণনা যোগ করুন',
  'View IPM options': 'আইপিএম-এর উপায় দেখুন',
  'Install a trap': 'ফাঁদ বসান',
  'PRAHARI has no pest with a published economic threshold for this crop, so a trap count could not be judged against anything.':
    'এই ফসলের কোনো পোকার প্রকাশিত অর্থনৈতিক সীমা প্রহরীর কাছে নেই, তাই ফাঁদের গণনা কিছুর সঙ্গে মিলিয়ে বিচার করা যাবে না।',
  'Trap type': 'ফাঁদের ধরন',
  'Install trap': 'ফাঁদ বসান',
  'Trap count': 'ফাঁদের গণনা',
  'You may attach a photograph of the trap, but PRAHARI does not claim to count insects from it. Your own number is what gets recorded.':
    'চাইলে ফাঁদের ছবি দিতে পারেন, কিন্তু প্রহরী ছবি থেকে পোকা গোনার দাবি করে না। আপনি যে সংখ্যা দেবেন, সেটাই লেখা হবে।',
  'Photograph of the trap (optional)': 'ফাঁদের ছবি (ইচ্ছামতো)',
  'Alerts': 'সতর্কবার্তা',
  'No alerts yet': 'এখনও কোনো সতর্কবার্তা নেই',
  'You will see risk warnings, threshold crossings and expert verdicts here.':
    'ঝুঁকির সতর্কতা, সীমা পেরোনো আর বিশেষজ্ঞের মতামত এখানে দেখতে পাবেন।',
  'Follow-up scan': 'পুনঃস্ক্যান',
  'Did the action work?': 'ব্যবস্থায় কাজ হয়েছে কি?',
  'Photograph an affected leaf in the same field. PRAHARI compares it with the first scan and reports the DIRECTION of change — never a percentage, because two hand-held photographs of different leaves cannot support one.':
    'একই জমির একটি আক্রান্ত পাতার ছবি তুলুন। প্রহরী সেটি প্রথম স্ক্যানের সঙ্গে মিলিয়ে শুধু বলবে অবস্থা ভালোর দিকে না খারাপের দিকে — কোনো শতাংশ নয়, কারণ হাতে তোলা দুটি আলাদা পাতার ছবি থেকে শতাংশ বলা যায় না।',
  'Compare with the first scan': 'প্রথম স্ক্যানের সঙ্গে মেলান',
  'Cannot take a comparable photo?': 'মেলানোর মতো ছবি তুলতে পারছেন না?',
  'Tell PRAHARI what you saw. It is stored as SELF-REPORTED, not as a measured comparison.':
    'আপনি কী দেখেছেন প্রহরীকে বলুন। এটি "নিজের দেওয়া তথ্য" হিসেবে রাখা হবে, মাপা তুলনা হিসেবে নয়।',
  'Could not be compared': 'মেলানো যায়নি',
  'Self-reported': 'নিজের দেওয়া তথ্য',
  'This is your own account, not a measured comparison of two photographs, so it is not counted as evidence that the treatment worked.':
    'এটা আপনার নিজের বিবরণ, দুটি ছবির মাপা তুলনা নয় — তাই চিকিৎসায় কাজ হয়েছে, এর প্রমাণ হিসেবে এটি ধরা হয় না।',
  'Lesions in the first scan': 'প্রথম স্ক্যানে দাগ',
  'Lesions now': 'এখন দাগ',
  'Producer organisation (FPO)': 'কৃষক উৎপাদক সংগঠন (এফপিও)',
  'Leave': 'ছেড়ে দিন',
  'Join': 'যোগ দিন',
  'Profile': 'প্রোফাইল',
  'field(s) registered': 'টি জমি নথিভুক্ত',
  'Sprays avoided': 'যত স্প্রে এড়ানো গেছে',
  'applications avoided': 'বার প্রয়োগ এড়ানো গেছে',
  'estimated saving': 'আনুমানিক সাশ্রয়',
  'Language': 'ভাষা',
  'Demo scenarios': 'ডেমো পরিস্থিতি',
  'System status': 'সিস্টেমের অবস্থা',

  // ── decision screen (summit pass) ─────────────────────────────────────
  'What should I do?': 'আমি কী করব?',
  'How serious is it?': 'কতটা গুরুতর?',
  'What to do now': 'এখন কী করবেন',
  'done': 'হয়েছে',
  'done today': 'আজ হয়েছে',
  'Mark done for today': 'আজকের মতো হয়েছে',
  'Ticks stay on this phone for today. Only a saved count or inspection changes the decision.':
    'টিক আজকের জন্য এই ফোনেই থাকে। সিদ্ধান্ত বদলায় শুধু নথিভুক্ত গণনা বা পরিদর্শনে।',
  'Scan': 'স্ক্যান', 'Count': 'গুনুন', 'See': 'দেখুন', 'Re-scan': 'আবার স্ক্যান', 'Inspect': 'পরিদর্শন',
  'Scan now': 'এখনই স্ক্যান করুন', 'Count trap': 'ফাঁদ গুনুন', 'Open plan': 'পরিকল্পনা দেখুন',
  'See reports': 'খবরগুলো দেখুন', 'Open record': 'খাতা খুলুন',
  'Record a new inspection': 'নতুন পরিদর্শন লিখুন',
  'Threshold today': 'আজকের সীমা',
  'Last count': 'শেষ গণনা',
  'Record today’s count': 'আজকের গণনা লিখুন',
  'Count the trap (or the plants) and enter the number. Nothing is decided from a photograph alone.':
    'ফাঁদের (বা গাছের) পোকা গুনে সংখ্যাটা লিখুন। শুধু ছবি দেখে কোনো সিদ্ধান্ত নেওয়া হয় না।',
  'preview, not saved yet': 'আগাম হিসাব — এখনও সংরক্ষণ হয়নি',
  'No published threshold for this pest on this crop — the count is recorded, but it cannot be judged against one.':
    'এই ফসলে এই পোকার প্রকাশিত কোনো সীমা নেই — গণনা লেখা থাকবে, কিন্তু কিছুর সঙ্গে মিলিয়ে বিচার করা যাবে না।',
  'Your IPM plan': 'আপনার আইপিএম পরিকল্পনা',
  'cheapest first': 'আগে সবচেয়ে সস্তা উপায়',
  'Start here': 'এখান থেকে শুরু করুন',
  'Costs nothing': 'কোনো খরচ নেই',
  'These steps are in today’s checklist above. The next rung opens only if your count or inspection shows the problem is building.':
    'এই কাজগুলো ওপরের আজকের তালিকায় আছে। গণনা বা পরিদর্শনে সমস্যা বাড়তে দেখা গেলে তবেই পরের ধাপ খুলবে।',
  'What would open this rung': 'এই ধাপ কখন খুলবে',
  'A saved count over a published threshold': 'প্রকাশিত সীমার বেশি একটি নথিভুক্ত গণনা',
  'A field inspection showing the disease is established, not a photograph alone':
    'শুধু ছবি নয় — জমি পরিদর্শনে রোগ জাঁকিয়ে বসার প্রমাণ',
  'A label claim for this crop and target verified by a named person against the CIB&RC register':
    'এই ফসল ও এই সমস্যার জন্য CIB&RC তালিকার সঙ্গে মিলিয়ে নির্দিষ্ট ব্যক্তির যাচাই করা লেবেল-অনুমোদন',
  'Why PRAHARI says this': 'প্রহরী কেন এটা বলছে',
  'Field evidence': 'জমির প্রমাণ',
  'Field measurement': 'জমির মাপ',
  'Not measured yet': 'এখনও মাপা হয়নি',
  'Pest activity': 'পোকার উপস্থিতির ধারা',
  'What you can do': 'আপনি যা করতে পারেন',
  'Verified chemical options': 'যাচাই করা রাসায়নিক উপায়',
  'Follow-up': 'পুনঃপরীক্ষা',
  'Field health history': 'জমির স্বাস্থ্যের ইতিহাস',
  'Field conditions': 'জমির অবস্থা',
  'No weather for this field right now': 'এই মুহূর্তে এই জমির আবহাওয়ার তথ্য নেই',
  'Not known': 'জানা নেই',
  'More': 'আরও',
  'More detail': 'আরও বিস্তারিত',
  'Assess, act, monitor': 'পরিদর্শন, ব্যবস্থা, নজরদারি',
  'Next field check': 'পরের জমি পরিদর্শন',
  'Need help?': 'সাহায্য দরকার?',
  'An expert would help here because:': 'এখানে বিশেষজ্ঞের সাহায্য কাজে লাগবে, কারণ:',
  'Needs field confirmation': 'জমিতে যাচাই দরকার',
  'Where is this field heading?': 'জমির অবস্থা কোন দিকে যাচ্ছে?',
  'Something was detected, but how much of it is in the field is not known yet. Only a count or an inspection can say.':
    'কিছু একটা ধরা পড়েছে, কিন্তু জমিতে তা কতটা আছে এখনও জানা নেই। শুধু গণনা বা পরিদর্শনই তা বলতে পারে।',
  'At the action threshold': 'ব্যবস্থা নেওয়ার সীমায় পৌঁছেছে',
  'Approaching the threshold': 'সীমার কাছাকাছি',
  'Below the threshold': 'সীমার নিচে',
  'Your count has reached the published action threshold for this crop and stage.':
    'আপনার গণনা এই ফসল ও ধাপের প্রকাশিত সীমায় পৌঁছেছে।',
  'Your count is over halfway to the published action threshold. Keep counting.':
    'আপনার গণনা প্রকাশিত সীমার অর্ধেক পেরিয়েছে। গোনা চালিয়ে যান।',
  'Your count is well below the published action threshold.': 'আপনার গণনা প্রকাশিত সীমার অনেক নিচে।',
  'Widespread in what you inspected': 'যত গাছ দেখেছেন, তার অনেকটায় ছড়িয়েছে',
  'Present in what you inspected': 'যত গাছ দেখেছেন, তার কয়েকটিতে আছে',
  'Few plants affected': 'অল্প কয়েকটি গাছ আক্রান্ত',
  'More than a third of the plants you walked showed it. Widen the inspection to a part of the field you have not walked.':
    'আপনি যত গাছ দেখেছেন তার এক-তৃতীয়াংশের বেশিতে লক্ষণ আছে। জমির যে অংশ দেখেননি, সেখানেও পরিদর্শন করুন।',
  'It is in the field but not through it. Walking a second stretch tells you whether it is spreading.':
    'জমিতে আছে, কিন্তু সারা জমিতে নয়। আরেকটা অংশ ঘুরে দেখলে বোঝা যাবে ছড়াচ্ছে কি না।',
  'Only a few of the plants you walked showed it.': 'আপনি যত গাছ দেখেছেন, তার অল্প কয়েকটিতে লক্ষণ আছে।',
  'Action threshold': 'ব্যবস্থা নেওয়ার সীমা',
  'Diagnosis': 'রোগ নির্ণয়',
  'Pest life stage': 'পোকার জীবনচক্রের ধাপ',
  'Label claim': 'লেবেল-অনুমোদন',
  'Field assessment': 'জমি পরিদর্শন',
  'Infection model': 'সংক্রমণ মডেল',
  'Cultural': 'চাষের পদ্ধতি', 'Mechanical': 'হাতে-কলমে', 'Biological': 'জৈব', 'Chemical': 'রাসায়নিক',
  'Assess': 'পরিদর্শন', 'Act': 'ব্যবস্থা', 'Monitor': 'নজরদারি',
  'Not yet': 'এখনও নয়', 'Logged': 'লেখা আছে', 'Start at the lowest rung': 'সবচেয়ে নিচের ধাপ থেকে শুরু',
  'Re-check set': 'পুনঃপরীক্ষার দিন ঠিক', 'After you act': 'ব্যবস্থা নেওয়ার পরে',
  'Improving': 'ভালোর দিকে', 'Stable': 'স্থির', 'Worsening': 'খারাপের দিকে', 'Not known yet': 'এখনও জানা নেই',
  'A few spots': 'কয়েকটি দাগ', 'Several leaves': 'বেশ কয়েকটি পাতা', 'Most of the plant': 'গাছের বেশিরভাগ',
  'Lower leaves': 'নিচের পাতা', 'Upper leaves': 'ওপরের পাতা', 'Stem': 'কাণ্ড', 'Fruit': 'ফল',
  'Medium': 'মাঝারি',
  'Feels like': 'অনুভূত', 'Humidity': 'আর্দ্রতা', 'Rain': 'বৃষ্টি', 'Wind': 'বাতাস',
  'Field outlook': 'জমির জন্য সামনের দিনগুলো',
  'Live': 'সরাসরি',
  'Demo weather • live provider unavailable': 'ডেমো আবহাওয়া • আসল পরিষেবা পাওয়া যাচ্ছে না',
  'Recent reading': 'সাম্প্রতিক মাপ',

  // ── risk levels (levelLabel) ──────────────────────────────────────────
  'Low': 'কম',
  'Watch': 'নজর রাখুন',
  'Rising': 'বাড়ছে',
  'Moderate': 'মাঝারি',
  'Good': 'ভালো',
}

/* Keyed dictionary for t(lang, key) in ui.jsx. */
export const BN_KEYS = {
  home: 'হোম', fields: 'জমি', scan: 'স্ক্যান', alerts: 'সতর্কবার্তা', profile: 'প্রোফাইল',
  health: 'ফসলের স্বাস্থ্য', whatsChanging: 'কী বদলাচ্ছে?', quickActions: 'দ্রুত কাজ',
  scanCrop: 'ফসল স্ক্যান', pestTrap: 'পোকার ফাঁদ', shouldISpray: 'স্প্রে করব কি?',
  advisory: 'পরামর্শ', forecast: 'পূর্বাভাস', why: 'কেন?', seeDetails: 'বিস্তারিত দেখুন',
  diagnosis: 'রোগ নির্ণয়', confidence: 'নিশ্চয়তা', alternatives: 'অন্য সম্ভাবনা',
  evidence: 'যে প্রমাণ পাওয়া গেছে', whatsNext: 'এরপর কী?', viewManagement: 'ব্যবস্থাপনা দেখুন',
  signIn: 'সাইন ইন', signUp: 'নতুন অ্যাকাউন্ট', signOut: 'সাইন আউট',
  mobile: 'মোবাইল নম্বর', password: 'পাসওয়ার্ড', name: 'পুরো নাম', village: 'গ্রাম', taluka: 'ব্লক',
  addField: 'জমি যোগ করুন', crop: 'ফসল', area: 'আয়তন (একর)', sowing: 'বোনার তারিখ',
  save: 'সংরক্ষণ করুন', cancel: 'বাতিল', retake: 'আরেকটি ছবি তুলুন', sendExpert: 'বিশেষজ্ঞকে পাঠান',
  count: 'গণনা', recheck: 'আবার পরীক্ষা', loading: 'লোড হচ্ছে…',
  offline: 'অফলাইন', synced: 'পাঠানো হয়েছে', timeline: 'জমির ইতিহাস',
  riskForecast: 'ঝুঁকির পূর্বাভাস', ipm: 'আইপিএম সুপারিশ', expert: 'বিশেষজ্ঞ',
}

export default BN
