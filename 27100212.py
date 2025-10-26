"""
Instagram Post Generator using OpenAI GPT-5 Responses API
Enhanced Version with Carousel Support

This Flask application creates Instagram posts by:
1. Planning the post and determining if it needs a single image or carousel
2. Generating visual images using GPT Image 1 (multiple for carousels)
3. Creating an engaging caption
All steps use conversation chaining to maintain context.
"""

from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os
import json
import base64
from datetime import datetime
import sqlite3
from pathlib import Path

app = Flask(__name__)

# Initialize OpenAI client
# SECURITY NOTE: Store your API key in an environment variable or .env file
# Never commit your API key to version control
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "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"))

# Database setup for storing Instagram posts with carousel support
def init_db():
    """
    Initialize SQLite database to store generated Instagram posts.
    Updated schema supports both single images and carousel posts.
    """
    conn = sqlite3.connect('instagram_posts.db')
    c = conn.cursor()
    
    # Main posts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headline TEXT NOT NULL,
            content TEXT NOT NULL,
            news_link TEXT NOT NULL,
            post_type TEXT NOT NULL,
            plan TEXT,
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Images table for storing multiple images per post (carousel support)
    c.execute('''
        CREATE TABLE IF NOT EXISTS post_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            image_url TEXT NOT NULL,
            image_prompt TEXT,
            sequence_order INTEGER NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database when app starts
init_db()

# Create static/images directory for storing generated images
static_images_dir = Path("static/images")
static_images_dir.mkdir(parents=True, exist_ok=True)

@app.route('/')
def index():
    """Render the main page with the input form"""
    return render_template('instagram_generator.html')

@app.route('/generate', methods=['POST'])
def generate_post():
    """
    Main endpoint that orchestrates the Instagram post generation.
    Uses conversation chaining with previous_response_id.
    Supports both single image posts and carousel posts (2-10 images).
    """
    try:
        # Get input data from the form
        data = request.json
        headline = data.get('headline')
        content = data.get('content')
        news_link = data.get('news_link')
        
        if not all([headline, content, news_link]):
            return jsonify({'error': 'All fields are required'}), 400
        
        # Step 1: Plan the Instagram post using web search
        # This step determines if we need a single image or carousel
        print("Step 1: Planning Instagram post with web search...")
        planning_response = client.responses.create(
            model="gpt-5",
            reasoning={"effort": "medium"},
            tools=[{"type": "web_search"}],
            input=f"""You are an expert social media strategist. I need to create an Instagram post about this news:

Headline: {headline}
Content: {content}
News Link: {news_link}

Please search the web to understand the context and current conversation around this topic. Then create a strategic plan for an Instagram post.

IMPORTANT: First, determine if this news story is best told as:
- SINGLE IMAGE: One powerful visual (use for simple announcements, single moments, straightforward news)
- CAROUSEL: Multiple images (2-10 slides) to tell a story, show progression, compare things, or break down complex information

For CAROUSEL posts, consider using multiple images when:
- The story has multiple key moments or aspects
- There's a before/after or progression to show
- Complex information needs to be broken down step-by-step
- Multiple perspectives or angles would enhance understanding
- There are several important people/places/things to feature

After deciding the post type, provide a detailed plan including:
- Post type decision: "SINGLE" or "CAROUSEL"
- If carousel, specify number of images needed (2-10)
- Visual concept for each image
- Tone and style
- Key messages to emphasize
- Hashtag suggestions
- Caption structure

Format your response clearly with:
POST_TYPE: [SINGLE or CAROUSEL]
IMAGE_COUNT: [number]
[rest of your plan]""",
            store=True
        )
        
        plan_text = planning_response.output_text
        planning_response_id = planning_response.id
        
        # Parse the plan to extract post type and image count
        post_type = "SINGLE"  # Default
        image_count = 1
        
        # Extract post type from the plan
        for line in plan_text.split('\n'):
            if 'POST_TYPE:' in line.upper():
                if 'CAROUSEL' in line.upper():
                    post_type = "CAROUSEL"
                break
        
        # Extract image count for carousel posts
        if post_type == "CAROUSEL":
            for line in plan_text.split('\n'):
                if 'IMAGE_COUNT:' in line.upper():
                    try:
                        # Extract the number from the line
                        count_str = ''.join(filter(str.isdigit, line))
                        if count_str:
                            image_count = max(2, min(10, int(count_str)))  # Clamp between 2-10
                    except:
                        image_count = 3  # Default carousel size
                    break
        
        print(f"Post type: {post_type}, Image count: {image_count}")
        
        # Step 2: Generate image(s) based on post type
        generated_images = []
        last_response_id = planning_response_id
        
        if post_type == "SINGLE":
            # Generate a single image
            print("Step 2: Generating single image...")
            image_data = generate_single_image(last_response_id, 1, 1)
            generated_images.append(image_data)
            last_response_id = image_data['response_id']
            
        else:  # CAROUSEL
            # Generate multiple images with conversation chaining
            print(f"Step 2: Generating {image_count} images for carousel...")
            for i in range(image_count):
                print(f"  Generating image {i+1} of {image_count}...")
                image_data = generate_carousel_image(last_response_id, i+1, image_count)
                generated_images.append(image_data)
                last_response_id = image_data['response_id']
        
        # Step 3: Generate the Instagram caption
        print("Step 3: Generating caption...")
        
        # Build context about all generated images
        images_context = "\n".join([
            f"Image {i+1}: {img['prompt']}" 
            for i, img in enumerate(generated_images)
        ])
        
        caption_response = client.responses.create(
            model="gpt-5",
            reasoning={"effort": "medium"},
            previous_response_id=last_response_id,
            input=f"""Now create the perfect Instagram caption for this {post_type.lower()} post. You have:
- The strategic plan you created
- Generated {len(generated_images)} image(s):
{images_context}

Write an engaging Instagram caption that:
1. Hooks the reader in the first line (this is critical!)
2. Tells the story from the news effectively
3. {"Guides viewers through the carousel slides" if post_type == "CAROUSEL" else "Complements the visual"}
4. Includes relevant emojis naturally (don't overuse them)
5. Has line breaks for readability
6. Ends with a call-to-action or thought-provoking question
7. Includes 8-12 relevant hashtags at the end

{"For carousel posts: Consider adding slide numbers or guiding language like 'Swipe to see...'" if post_type == "CAROUSEL" else ""}

Make it authentic, engaging, and optimized for Instagram's algorithm.
The caption should be ready to copy and paste directly into Instagram.

Original news link to reference: {news_link}""",
            store=True
        )
        
        caption = caption_response.output_text
        
        # Store the generated post in the database
        conn = sqlite3.connect('instagram_posts.db')
        c = conn.cursor()
        
        # Insert main post record
        c.execute('''
            INSERT INTO posts (headline, content, news_link, post_type, plan, caption)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (headline, content, news_link, post_type, plan_text, caption))
        post_id = c.lastrowid
        
        # Insert all images
        for i, img in enumerate(generated_images):
            c.execute('''
                INSERT INTO post_images (post_id, image_url, image_prompt, sequence_order)
                VALUES (?, ?, ?, ?)
            ''', (post_id, img['url'], img['prompt'], i))
        
        conn.commit()
        conn.close()
        
        print(f"Post saved to database with ID: {post_id}")
        
        # Return all the generated content
        return jsonify({
            'success': True,
            'post_id': post_id,
            'post_type': post_type,
            'plan': plan_text,
            'images': [{'url': img['url'], 'prompt': img['prompt']} for img in generated_images],
            'caption': caption,
            'message': f'Instagram {post_type.lower()} post generated successfully!'
        })
        
    except Exception as e:
        print(f"Error generating post: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def generate_single_image(previous_response_id, image_num, total_images):
    """
    Generate a single image for a single-image post.
    Uses conversation chaining to maintain context.
    """
    # Ask GPT-5 to create a detailed image prompt
    image_prompt_response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "low"},
        previous_response_id=previous_response_id,
        input="""Based on the plan you just created, write a detailed GPT Image 1 generation prompt that will create the perfect Instagram visual. 

The prompt should be:
- Highly detailed and specific
- Describe composition, style, colors, and mood
- Be optimized for square Instagram format (1:1 aspect ratio)
- Create something eye-catching and shareable
- Professional and polished

Provide ONLY the image prompt, nothing else.""",
        store=True
    )
    
    image_prompt = image_prompt_response.output_text.strip()
    image_prompt_response_id = image_prompt_response.id
    
    # Generate the actual image
    return generate_and_save_image(image_prompt, image_prompt_response_id)


def generate_carousel_image(previous_response_id, image_num, total_images):
    """
    Generate one image in a carousel sequence.
    Uses conversation chaining to maintain narrative consistency.
    """
    # Ask GPT-5 to create a prompt for this specific carousel slide
    image_prompt_response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "low"},
        previous_response_id=previous_response_id,
        input=f"""Now create the prompt for IMAGE {image_num} of {total_images} in this carousel.

This is slide {image_num} of {total_images}, so:
- Maintain visual consistency with any previous slides (same style, color palette)
- Focus on the specific aspect of the story for this slide
- Ensure it works as part of the overall narrative sequence
- Make it compelling enough that viewers will want to swipe to the next image

The prompt should be:
- Highly detailed and specific
- Describe composition, style, colors, and mood
- Be optimized for square Instagram format (1:1 aspect ratio)
- Professional and polished
- Part of a cohesive visual story

Provide ONLY the image prompt for this slide, nothing else.""",
        store=True
    )
    
    image_prompt = image_prompt_response.output_text.strip()
    image_prompt_response_id = image_prompt_response.id
    
    # Generate the actual image
    return generate_and_save_image(image_prompt, image_prompt_response_id)


def generate_and_save_image(prompt, response_id):
    """
    Generate an image using GPT Image 1 and save it to disk.
    Returns a dictionary with the image URL, prompt, and response ID.
    """
    # Generate the actual image using GPT Image 1
    print(f"Calling GPT Image 1 to generate image...")
    image_response = client.images.generate(
        model="gpt-image-1-mini",
        prompt=prompt,
        size="1024x1024",  # Square format for Instagram
        quality="high",
        n=1
    )
    
    # Decode the base64 image data and save it
    image_base64 = image_response.data[0].b64_json
    
    # Generate a unique filename using timestamp and random component
    timestamp = int(datetime.now().timestamp() * 1000)  # Millisecond precision
    image_filename = f"instagram_{timestamp}.png"
    image_path = static_images_dir / image_filename
    
    # Decode and save the image
    image_bytes = base64.b64decode(image_base64)
    with open(image_path, 'wb') as f:
        f.write(image_bytes)
    
    # Create URL path for frontend
    image_url = f"/static/images/{image_filename}"
    print(f"Image saved successfully to: {image_url}")
    
    return {
        'url': image_url,
        'prompt': prompt,
        'response_id': response_id
    }


@app.route('/posts', methods=['GET'])
def get_posts():
    """Retrieve all stored Instagram posts with their images"""
    try:
        conn = sqlite3.connect('instagram_posts.db')
        c = conn.cursor()
        
        # Get all posts
        c.execute('''
            SELECT id, headline, content, news_link, post_type, plan, caption, created_at
            FROM posts
            ORDER BY created_at DESC
        ''')
        
        posts = []
        for row in c.fetchall():
            post_id = row[0]
            
            # Get all images for this post
            c.execute('''
                SELECT image_url, image_prompt, sequence_order
                FROM post_images
                WHERE post_id = ?
                ORDER BY sequence_order
            ''', (post_id,))
            
            images = [
                {
                    'url': img_row[0],
                    'prompt': img_row[1],
                    'order': img_row[2]
                }
                for img_row in c.fetchall()
            ]
            
            posts.append({
                'id': post_id,
                'headline': row[1],
                'content': row[2],
                'news_link': row[3],
                'post_type': row[4],
                'plan': row[5],
                'caption': row[6],
                'created_at': row[7],
                'images': images
            })
        
        conn.close()
        return jsonify({'posts': posts})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/post/<int:post_id>', methods=['GET'])
def get_post(post_id):
    """Retrieve a specific Instagram post by ID with all its images"""
    try:
        conn = sqlite3.connect('instagram_posts.db')
        c = conn.cursor()
        
        # Get post details
        c.execute('''
            SELECT id, headline, content, news_link, post_type, plan, caption, created_at
            FROM posts
            WHERE id = ?
        ''', (post_id,))
        
        row = c.fetchone()
        
        if not row:
            conn.close()
            return jsonify({'error': 'Post not found'}), 404
        
        # Get all images for this post
        c.execute('''
            SELECT image_url, image_prompt, sequence_order
            FROM post_images
            WHERE post_id = ?
            ORDER BY sequence_order
        ''', (post_id,))
        
        images = [
            {
                'url': img_row[0],
                'prompt': img_row[1],
                'order': img_row[2]
            }
            for img_row in c.fetchall()
        ]
        
        conn.close()
        
        post = {
            'id': row[0],
            'headline': row[1],
            'content': row[2],
            'news_link': row[3],
            'post_type': row[4],
            'plan': row[5],
            'caption': row[6],
            'created_at': row[7],
            'images': images
        }
        
        return jsonify({'post': post})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/delete/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    """Delete a post and all its associated images"""
    try:
        conn = sqlite3.connect('instagram_posts.db')
        c = conn.cursor()
        
        # Get image paths before deleting
        c.execute('SELECT image_url FROM post_images WHERE post_id = ?', (post_id,))
        image_urls = [row[0] for row in c.fetchall()]
        
        # Delete from database
        c.execute('DELETE FROM post_images WHERE post_id = ?', (post_id,))
        c.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        conn.commit()
        conn.close()
        
        # Delete image files from disk
        for url in image_urls:
            try:
                filename = url.split('/')[-1]
                image_path = static_images_dir / filename
                if image_path.exists():
                    image_path.unlink()
            except Exception as e:
                print(f"Error deleting image file {url}: {str(e)}")
        
        return jsonify({'success': True, 'message': 'Post deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Run the Flask development server
    print("Starting Instagram Post Generator...")
    print("Navigate to http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)