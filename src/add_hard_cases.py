import pandas as pd
import os


# ============================================================
# HARDER FINDBACK TEST CASES
# ============================================================

new_data = [

    # --------------------------------------------------------
    # HARD CASE 1 - Backpack
    # --------------------------------------------------------

    {
        "report_id": "FB013",
        "report_type": "Lost",
        "item_category": "Backpack",
        "description": "I misplaced my navy rucksack somewhere around the university library.",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-19",
        "approx_time": "10:15",
        "status": "Lost"
    },

    {
        "report_id": "FB014",
        "report_type": "Found",
        "item_category": "Backpack",
        "description": "A dark-blue daypack was discovered close to the reading hall.",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-19",
        "approx_time": "10:40",
        "status": "Found"
    },

    # Distractor for backpack
    {
        "report_id": "FB015",
        "report_type": "Found",
        "item_category": "Backpack",
        "description": "A navy backpack was found near the airport departure hall.",
        "organization_type": "Airport",
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Departure Hall",
        "date": "2026-08-19",
        "approx_time": "17:30",
        "status": "Found"
    },


    # --------------------------------------------------------
    # HARD CASE 2 - Wallet
    # --------------------------------------------------------

    {
        "report_id": "FB016",
        "report_type": "Lost",
        "item_category": "Wallet",
        "description": "My brown leather billfold went missing near the airport security checkpoint.",
        "organization_type": "Airport",
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Security Checkpoint",
        "date": "2026-08-19",
        "approx_time": "14:00",
        "status": "Lost"
    },

    {
        "report_id": "FB017",
        "report_type": "Found",
        "item_category": "Wallet",
        "description": "A leather money holder was found beside the security screening area.",
        "organization_type": "Airport",
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Security Checkpoint",
        "date": "2026-08-19",
        "approx_time": "14:25",
        "status": "Found"
    },


    # --------------------------------------------------------
    # HARD CASE 3 - Phone
    # --------------------------------------------------------

    {
        "report_id": "FB018",
        "report_type": "Lost",
        "item_category": "Phone",
        "description": "I cannot find my black mobile handset. I last remember having it near the cinema entrance.",
        "organization_type": "Mall",
        "organization_name": "City Center Mall",
        "campus_or_branch": "Main Branch",
        "building_or_terminal": "Entertainment Wing",
        "floor_or_level": "1st Floor",
        "specific_area": "Cinema Entrance",
        "date": "2026-08-19",
        "approx_time": "18:10",
        "status": "Lost"
    },

    {
        "report_id": "FB019",
        "report_type": "Found",
        "item_category": "Phone",
        "description": "A black smartphone was discovered outside the movie theater entrance.",
        "organization_type": "Mall",
        "organization_name": "City Center Mall",
        "campus_or_branch": "Main Branch",
        "building_or_terminal": "Entertainment Wing",
        "floor_or_level": "1st Floor",
        "specific_area": "Cinema Entrance",
        "date": "2026-08-19",
        "approx_time": "18:35",
        "status": "Found"
    },


    # --------------------------------------------------------
    # HARD CASE 4 - Laptop
    # --------------------------------------------------------

    {
        "report_id": "FB020",
        "report_type": "Lost",
        "item_category": "Laptop",
        "description": "I left my silver notebook computer with a blue sticker inside the engineering laboratory.",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Engineering Block",
        "floor_or_level": "3rd Floor",
        "specific_area": "Laboratory 3",
        "date": "2026-08-19",
        "approx_time": "12:20",
        "status": "Lost"
    },

    {
        "report_id": "FB021",
        "report_type": "Found",
        "item_category": "Laptop",
        "description": "A metallic laptop carrying a blue sticker was discovered in the engineering lab.",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Engineering Block",
        "floor_or_level": "3rd Floor",
        "specific_area": "Laboratory 3",
        "date": "2026-08-19",
        "approx_time": "12:45",
        "status": "Found"
    },


    # --------------------------------------------------------
    # HARD CASE 5 - Earbuds
    # --------------------------------------------------------

    {
        "report_id": "FB022",
        "report_type": "Lost",
        "item_category": "Earbuds",
        "description": "I misplaced my white wireless buds inside their charging case near airport security.",
        "organization_type": "Airport",
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Security Checkpoint",
        "date": "2026-08-19",
        "approx_time": "16:10",
        "status": "Lost"
    },

    {
        "report_id": "FB023",
        "report_type": "Found",
        "item_category": "Earbuds",
        "description": "A pair of white Bluetooth buds in a small case was found beside the security screening point.",
        "organization_type": "Airport",
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Security Checkpoint",
        "date": "2026-08-19",
        "approx_time": "16:35",
        "status": "Found"
    },


    # --------------------------------------------------------
    # HARD CASE 6 - Watch
    # --------------------------------------------------------

    {
        "report_id": "FB024",
        "report_type": "Lost",
        "item_category": "Watch",
        "description": "My dark smartwatch disappeared while I was sitting in the station waiting area.",
        "organization_type": "Railway Station",
        "organization_name": "Central Railway Station",
        "campus_or_branch": "Main Station",
        "building_or_terminal": "Main Concourse",
        "floor_or_level": "Ground Level",
        "specific_area": "Waiting Area",
        "date": "2026-08-19",
        "approx_time": "08:30",
        "status": "Lost"
    },

    {
        "report_id": "FB025",
        "report_type": "Found",
        "item_category": "Watch",
        "description": "A dark-colored smart wristwatch was discovered near the passenger waiting section.",
        "organization_type": "Railway Station",
        "organization_name": "Central Railway Station",
        "campus_or_branch": "Main Station",
        "building_or_terminal": "Main Concourse",
        "floor_or_level": "Ground Level",
        "specific_area": "Waiting Area",
        "date": "2026-08-19",
        "approx_time": "08:55",
        "status": "Found"
    }

]


# ============================================================
# ADD TO EXISTING DATASET
# ============================================================

file_path = "dataset/findback_reports.csv"


if not os.path.exists(file_path):

    print("ERROR: Dataset file was not found.")

else:

    df = pd.read_csv(file_path)

    new_df = pd.DataFrame(new_data)

    # Avoid duplicate IDs if script is accidentally run again
    existing_ids = set(df["report_id"])

    new_df = new_df[
        ~new_df["report_id"].isin(existing_ids)
    ]

    if len(new_df) == 0:

        print("No new records were added.")
        print("These hard cases already exist.")

    else:

        df = pd.concat(
            [df, new_df],
            ignore_index=True
        )

        df.to_csv(
            file_path,
            index=False
        )

        print("\n========================================")
        print("FINDBACK DATASET UPDATED")
        print("========================================")

        print(
            f"New reports added: {len(new_df)}"
        )

        print(
            f"Total reports now: {len(df)}"
        )

        print(
            "\nDataset saved to:"
        )

        print(
            file_path
        )

        print("========================================")