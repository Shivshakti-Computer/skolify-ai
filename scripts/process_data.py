import json
from pathlib import Path
from datetime import datetime


class DataProcessor:
    def __init__(self, chunk_size=400, chunk_overlap=80):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_pricing_facts(self):
        """Pricing facts JSON load karo"""
        pricing_file = Path('data/pricing_facts.json')
        if pricing_file.exists():
            with open(pricing_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def create_pricing_chunks(self, pricing_data):
        """
        Pricing data se structured chunks banao
        Ye chunks scraping se better hain
        """
        chunks = []
        plans = pricing_data['plans']
        addons = pricing_data['addons']
        credits = pricing_data['credits']
        trial = pricing_data['trial']
        limits = pricing_data['addon_limits']

        # ── Chunk 1: Plan Overview ──────────────────
        overview = """
        Skolify Pricing Plans Overview:
        
        Starter Plan: ₹499/month
        - 500 students (max 750 with add-on)
        - 20 teachers (max 30 with add-on)
        - 500 free credits/month
        - No credit rollover
        - 2 GB storage
        - 6 modules included
        
        Growth Plan: ₹999/month (Most Popular)
        - 1,500 students (max 2,250 with add-on)
        - 50 teachers (max 75 with add-on)
        - 1,500 free credits/month
        - 3 months credit rollover, max 4,500 carry forward
        - 10 GB storage
        - 13 modules included
        
        Pro Plan: ₹1,999/month
        - 5,000 students (max 7,000 with add-on)
        - 150 teachers (max 200 with add-on)
        - 3,000 free credits/month
        - 6 months credit rollover, max 18,000 carry forward
        - 50 GB storage
        - 16 modules included
        
        Enterprise Plan: ₹3,999/month
        - Unlimited students and teachers
        - 10,000 free credits/month
        - Credits never expire
        - Unlimited storage
        - 23 modules included
        - White-label option, API access
        
        All plans include 60-day free trial, no credit card required.
        Annual billing = 2 months free.
        """.strip()

        chunks.append({
            'text': overview,
            'metadata': {
                'url': 'https://skolify.in/pricing',
                'page_type': 'pricing',
                'title': 'Skolify Pricing Plans',
                'source': 'pricing_facts',
                'chunk_id': 0
            }
        })

        # ── Chunk 2: Per Student Cost ───────────────
        cost_chunk = """
        Skolify Per Student Monthly Cost - Most Affordable School ERP:
        
        Starter: ₹1.00/student/month (₹0.033/day) - 500 students base
        Growth: ₹0.67/student/month (₹0.022/day) - 1,500 students base
        Pro: ₹0.40/student/month (₹0.013/day) - 5,000 students base
        Enterprise: ₹0.40/student/month (₹0.013/day) - Unlimited students
        
        Industry average: ₹3-5/student/month
        Skolify: ₹0.33-₹1/student/month
        
        Starting price: ₹499/month for up to 500 students
        Yearly billing saves 2 months cost.
        """.strip()

        chunks.append({
            'text': cost_chunk,
            'metadata': {
                'url': 'https://skolify.in/pricing',
                'page_type': 'pricing',
                'title': 'Per Student Cost',
                'source': 'pricing_facts',
                'chunk_id': 1
            }
        })

        # ── Chunk 3: Credit System ──────────────────
        credit_chunk = """
        Skolify Credit System - Pay as you go messaging:
        
        Credit Value: 1 Credit = ₹1
        
        How credits work:
        - 1 SMS = 1 Credit
        - 1 WhatsApp message = 1 Credit
        - 10 Emails = 1 Credit (NOT 0.5, NOT 2)
        
        Free credits per plan:
        - Starter: 500 credits/month (no rollover, monthly reset)
        - Growth: 1,500 credits/month (3 months rollover, max 4,500)
        - Pro: 3,000 credits/month (6 months rollover, max 18,000)
        - Enterprise: 10,000 credits/month (never expire, unlimited)
        
        Extra credit packs (one-time, no subscription):
        - 250 credits = ₹199 (₹0.80/credit)
        - 700 credits = ₹499 (₹0.71/credit) - Most Popular
        - 1,500 credits = ₹999 (₹0.67/credit)
        - 3,500 credits = ₹1,999 (₹0.57/credit)
        
        Credits rollover: purchased packs rollover per plan rules.
        """.strip()

        chunks.append({
            'text': credit_chunk,
            'metadata': {
                'url': 'https://skolify.in/pricing',
                'page_type': 'pricing',
                'title': 'Credit System',
                'source': 'pricing_facts',
                'chunk_id': 2
            }
        })

        # ── Chunk 4: Add-ons ────────────────────────
        addon_chunk = """
        Skolify Add-ons - Extra students and teachers:
        
        Extra Student Add-ons (one-time purchase, permanent):
        - +50 students = ₹99 (₹1.98/student)
        - +100 students = ₹179 (₹1.79/student)
        - +250 students = ₹399 (₹1.60/student)
        - +500 students = ₹699 (₹1.40/student)
        
        Extra Teacher/Staff Add-ons (one-time purchase, permanent):
        - +5 staff = ₹99 (₹19.80/staff)
        - +10 staff = ₹179 (₹17.90/staff)
        - +25 staff = ₹399 (₹15.96/staff)
        
        Add-on limits per plan:
        Starter: base 500 + max 250 extra = 750 total students
                 base 20 + max 10 extra = 30 total teachers
        
        Growth: base 1,500 + max 750 extra = 2,250 total students
                base 50 + max 25 extra = 75 total teachers
        
        Pro: base 5,000 + max 2,000 extra = 7,000 total students
             base 150 + max 50 extra = 200 total teachers
        
        Enterprise: Unlimited students and teachers, no add-on needed.
        
        If add-on limit is full, plan upgrade is required.
        """.strip()

        chunks.append({
            'text': addon_chunk,
            'metadata': {
                'url': 'https://skolify.in/pricing',
                'page_type': 'pricing',
                'title': 'Add-ons Pricing',
                'source': 'pricing_facts',
                'chunk_id': 3
            }
        })

        # ── Chunk 5: Trial & FAQ ────────────────────
        trial_chunk = """
        Skolify Free Trial and Common Questions:
        
        Free Trial:
        - 60 days free trial
        - No credit card required
        - 500 free credits during trial
        - Setup takes only 15 minutes
        - Full access to all features
        
        Frequently Asked Questions:
        
        Q: Student limit puri ho jaaye to kya karein?
        A: Pehle extra student add-on kharid sakte ho (plan cap tak).
           Growth plan mein 1,500 base + 750 addon = 2,250 total possible.
           Cap full hone par plan upgrade karo.
        
        Q: Monthly se yearly switch kar sakte hain?
        A: Haan! Remaining days ka credit automatically adjust hota hai.
           Double charge nahi hota.
        
        Q: Cancel karne pe kya hota hai?
        A: Period end tak poora access milta rehta hai.
           Koi abrupt cutoff nahi hota.
        
        Q: Yearly billing kitna save karta hai?
        A: Starter: ₹989 save (₹4,999/year)
           Growth: ₹1,989 save (₹9,999/year)
           Pro: ₹3,989 save (₹19,999/year)
           Enterprise: ₹7,989 save (₹39,999/year)
        """.strip()

        chunks.append({
            'text': trial_chunk,
            'metadata': {
                'url': 'https://skolify.in/pricing',
                'page_type': 'pricing',
                'title': 'Trial and FAQ',
                'source': 'pricing_facts',
                'chunk_id': 4
            }
        })

        print(f"  ✅ Pricing facts: {len(chunks)} structured chunks")
        return chunks

    def chunk_text(self, text, metadata):
        words = text.split()
        chunks = []
        i = 0
        chunk_num = 0

        while i < len(words):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = ' '.join(chunk_words)
            chunks.append({
                'text': chunk_text,
                'metadata': {**metadata, 'chunk_id': chunk_num}
            })
            i += self.chunk_size - self.chunk_overlap
            chunk_num += 1

        return chunks

    def process_scraped_data(self, input_file):
        print(f"📂 Loading: {input_file}")

        with open(input_file, 'r', encoding='utf-8') as f:
            pages = json.load(f)

        print(f"📄 Pages found: {len(pages)}\n")

        all_chunks = []

        # ✅ Pricing facts pehle add karo
        pricing_data = self.load_pricing_facts()
        if pricing_data:
            print("💰 Adding structured pricing facts...")
            pricing_chunks = self.create_pricing_chunks(pricing_data)
            all_chunks.extend(pricing_chunks)
        else:
            print("⚠️ pricing_facts.json not found!")

        # ✅ Scraped pages process karo
        for page in pages:
            url = page['url']
            page_type = page['page_type']

            # Pricing page scraping skip karo
            # kyunki structured facts already add ho gaye
            if page_type == 'pricing':
                print(f"⏭️  Skipping scraped pricing (using facts): {url}")
                continue

            print(f"Processing [{page_type}]: {url}")

            metadata = {
                'url': url,
                'page_type': page_type,
                'title': page['title'],
                'source': 'website',
            }

            headings_text = ""
            if page.get('headings'):
                all_h = (
                    page['headings'].get('h1', []) +
                    page['headings'].get('h2', []) +
                    page['headings'].get('h3', [])
                )
                headings_text = "Headings: " + " | ".join(all_h) + ". "

            full_text = f"{headings_text}{page['text_content']}"
            chunks = self.chunk_text(full_text, metadata)
            all_chunks.extend(chunks)

            print(f"  ✅ {len(chunks)} chunks")

        print(f"\n✅ Total chunks: {len(all_chunks)}")

        output_dir = Path('data/processed')
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = (
            output_dir /
            f'chunks_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, indent=2, ensure_ascii=False)

        print(f"💾 Saved: {output_file}")
        return all_chunks


if __name__ == '__main__':
    processor = DataProcessor(chunk_size=400, chunk_overlap=80)

    raw_files = list(Path('data/raw').glob('scraped_data_*.json'))
    if not raw_files:
        print("❌ No scraped data! Run scrape_website.py first")
        exit(1)

    latest_file = max(raw_files, key=lambda p: p.stat().st_mtime)
    processor.process_scraped_data(latest_file)